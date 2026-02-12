// EVOLVE-BLOCK-START
Status DBImpl::WriteImpl(const WriteOptions& write_options,
                         WriteBatch* my_batch, WriteCallback* callback,
                         UserWriteCallback* user_write_cb, uint64_t* wal_used,
                         uint64_t log_ref, bool disable_memtable,
                         uint64_t* seq_used, size_t batch_cnt,
                         PreReleaseCallback* pre_release_callback,
                         PostMemTableCallback* post_memtable_callback,
                         std::shared_ptr<WriteBatchWithIndex> wbwi) {
  assert(!seq_per_batch_ || batch_cnt != 0);
  assert(my_batch == nullptr || my_batch->Count() == 0 ||
         write_options.protection_bytes_per_key == 0 ||
         write_options.protection_bytes_per_key ==
             my_batch->GetProtectionBytesPerKey());
  if (my_batch == nullptr) {
    return Status::InvalidArgument("Batch is nullptr!");
  } else if (!disable_memtable &&
             WriteBatchInternal::TimestampsUpdateNeeded(*my_batch)) {
    // If writing to memtable, then we require the caller to set/update the
    // timestamps for the keys in the write batch.
    // Otherwise, it means we are just writing to the WAL, and we allow
    // timestamps unset for the keys in the write batch. This can happen if we
    // use TransactionDB with write-committed policy, and we currently do not
    // support user-defined timestamp with other policies.
    // In the prepare phase, a transaction can write the batch to the WAL
    // without inserting to memtable. The keys in the batch do not have to be
    // assigned timestamps because they will be used only during recovery if
    // there is a commit marker which includes their commit timestamp.
    return Status::InvalidArgument("write batch must have timestamp(s) set");
  } else if (write_options.rate_limiter_priority != Env::IO_TOTAL &&
             write_options.rate_limiter_priority != Env::IO_USER) {
    return Status::InvalidArgument(
        "WriteOptions::rate_limiter_priority only allows "
        "Env::IO_TOTAL and Env::IO_USER due to implementation constraints");
  } else if (write_options.rate_limiter_priority != Env::IO_TOTAL &&
             (write_options.disableWAL || manual_wal_flush_)) {
    return Status::InvalidArgument(
        "WriteOptions::rate_limiter_priority currently only supports "
        "rate-limiting automatic WAL flush, which requires "
        "`WriteOptions::disableWAL` and "
        "`DBOptions::manual_wal_flush` both set to false");
  } else if (write_options.protection_bytes_per_key != 0 &&
             write_options.protection_bytes_per_key != 8) {
    return Status::InvalidArgument(
        "`WriteOptions::protection_bytes_per_key` must be zero or eight");
  } else if (write_options.disableWAL &&
             immutable_db_options_.recycle_log_file_num > 0 &&
             !(two_write_queues_ && disable_memtable)) {
    // Corruption detection in recycled WALs relies on sequential sequence
    // numbers, but WritePreparedTxnDB uses disableWAL internally for split
    // writes
    return Status::InvalidArgument(
        "WriteOptions::disableWAL option is not supported if "
        "DBOptions::recycle_log_file_num > 0");
  }
  // TODO: this use of operator bool on `tracer_` can avoid unnecessary lock
  // grabs but does not seem thread-safe.
  if (tracer_) {
    InstrumentedMutexLock lock(&trace_mutex_);
    if (tracer_ && !tracer_->IsWriteOrderPreserved()) {
      // We don't have to preserve write order so can trace anywhere. It's more
      // efficient to trace here than to add latency to a phase of the log/apply
      // pipeline.
      // TODO: maybe handle the tracing status?
      tracer_->Write(my_batch).PermitUncheckedError();
    }
  }
  if (write_options.sync && write_options.disableWAL) {
    return Status::InvalidArgument("Sync writes has to enable WAL.");
  }
  if (two_write_queues_ && immutable_db_options_.enable_pipelined_write) {
    return Status::NotSupported(
        "pipelined_writes is not compatible with concurrent prepares");
  }
  if (seq_per_batch_ && immutable_db_options_.enable_pipelined_write) {
    // TODO(yiwu): update pipeline write with seq_per_batch and batch_cnt
    return Status::NotSupported(
        "pipelined_writes is not compatible with seq_per_batch");
  }
  if (immutable_db_options_.unordered_write &&
      immutable_db_options_.enable_pipelined_write) {
    return Status::NotSupported(
        "pipelined_writes is not compatible with unordered_write");
  }
  if (immutable_db_options_.enable_pipelined_write &&
      post_memtable_callback != nullptr) {
    return Status::NotSupported(
        "pipelined write currently does not honor post_memtable_callback");
  }
  if (seq_per_batch_ && post_memtable_callback != nullptr) {
    return Status::NotSupported(
        "seq_per_batch currently does not honor post_memtable_callback");
  }
  if (my_batch->HasDeleteRange() && immutable_db_options_.row_cache) {
    return Status::NotSupported(
        "DeleteRange is not compatible with row cache.");
  }
  // Whether the WBWI is from transaction commit or a direct write
  // (IngestWriteBatchWithIndex())
  bool ingest_wbwi_for_commit = false;
  if (wbwi) {
    if (my_batch->HasCommit()) {
      ingest_wbwi_for_commit = true;
      assert(log_ref);
    } else {
      // Only supports disableWAL for directly ingesting WBWI for now.
      assert(write_options.disableWAL);
    }
    assert(!callback);
    if (immutable_db_options_.unordered_write) {
      return Status::NotSupported(
          "Ingesting WriteBatch does not support unordered_write");
    }
    if (immutable_db_options_.enable_pipelined_write) {
      return Status::NotSupported(
          "Ingesting WriteBatch does not support pipelined_write");
    }
    if (!wbwi->GetOverwriteKey()) {
      return Status::NotSupported(
          "WriteBatchWithIndex ingestion requires overwrite_key=true");
    }
  }
  // Otherwise IsLatestPersistentState optimization does not make sense
  assert(!WriteBatchInternal::IsLatestPersistentState(my_batch) ||
         disable_memtable);

  if (write_options.low_pri) {
    Status s = ThrottleLowPriWritesIfNeeded(write_options, my_batch);
    if (!s.ok()) {
      return s;
    }
  }

  if (two_write_queues_ && disable_memtable) {
    AssignOrder assign_order =
        seq_per_batch_ ? kDoAssignOrder : kDontAssignOrder;
    // Otherwise it is WAL-only Prepare batches in WriteCommitted policy and
    // they don't consume sequence.
    return WriteImplWALOnly(
        &nonmem_write_thread_, write_options, my_batch, callback, user_write_cb,
        wal_used, log_ref, seq_used, batch_cnt, pre_release_callback,
        assign_order, kDontPublishLastSeq, disable_memtable);
  }

  if (immutable_db_options_.unordered_write) {
    const size_t sub_batch_cnt = batch_cnt != 0
                                     ? batch_cnt
                                     // every key is a sub-batch consuming a seq
                                     : WriteBatchInternal::Count(my_batch);
    uint64_t seq = 0;
    // Use a write thread to i) optimize for WAL write, ii) publish last
    // sequence in in increasing order, iii) call pre_release_callback serially
    Status status = WriteImplWALOnly(
        &write_thread_, write_options, my_batch, callback, user_write_cb,
        wal_used, log_ref, &seq, sub_batch_cnt, pre_release_callback,
        kDoAssignOrder, kDoPublishLastSeq, disable_memtable);
    TEST_SYNC_POINT("DBImpl::WriteImpl:UnorderedWriteAfterWriteWAL");
    if (!status.ok()) {
      return status;
    }
    if (seq_used) {
      *seq_used = seq;
    }
    if (!disable_memtable) {
      TEST_SYNC_POINT("DBImpl::WriteImpl:BeforeUnorderedWriteMemtable");
      status = UnorderedWriteMemtable(write_options, my_batch, callback,
                                      log_ref, seq, sub_batch_cnt);
    }
    return status;
  }

  if (immutable_db_options_.enable_pipelined_write) {
    return PipelinedWriteImpl(write_options, my_batch, callback, user_write_cb,
                              wal_used, log_ref, disable_memtable, seq_used);
  }

  PERF_TIMER_GUARD(write_pre_and_post_process_time);
  WriteThread::Writer w(write_options, my_batch, callback, user_write_cb,
                        log_ref, disable_memtable, batch_cnt,
                        pre_release_callback, post_memtable_callback,
                        /*_ingest_wbwi=*/wbwi != nullptr);
  StopWatch write_sw(immutable_db_options_.clock, stats_, DB_WRITE);

  write_thread_.JoinBatchGroup(&w);
  if (w.state == WriteThread::STATE_PARALLEL_MEMTABLE_CALLER) {
    write_thread_.SetMemWritersEachStride(&w);
  }
  if (w.state == WriteThread::STATE_PARALLEL_MEMTABLE_WRITER) {
    // we are a non-leader in a parallel group

    if (w.ShouldWriteToMemtable()) {
      PERF_TIMER_STOP(write_pre_and_post_process_time);
      PERF_TIMER_FOR_WAIT_GUARD(write_memtable_time);

      ColumnFamilyMemTablesImpl column_family_memtables(
          versions_->GetColumnFamilySet());
      w.status = WriteBatchInternal::InsertInto(
          &w, w.sequence, &column_family_memtables, &flush_scheduler_,
          &trim_history_scheduler_,
          write_options.ignore_missing_column_families, 0 /*log_number*/, this,
          true /*concurrent_memtable_writes*/, seq_per_batch_, w.batch_cnt,
          batch_per_txn_, write_options.memtable_insert_hint_per_batch);

      PERF_TIMER_START(write_pre_and_post_process_time);
    }

    if (write_thread_.CompleteParallelMemTableWriter(&w)) {
      // we're responsible for exit batch group
      // TODO(myabandeh): propagate status to write_group
      auto last_sequence = w.write_group->last_sequence;
      for (auto* tmp_w : *(w.write_group)) {
        assert(tmp_w);
        if (tmp_w->post_memtable_callback) {
          Status tmp_s =
              (*tmp_w->post_memtable_callback)(last_sequence, disable_memtable);
          // TODO: propagate the execution status of post_memtable_callback to
          // caller.
          assert(tmp_s.ok());
        }
      }
      if (w.status.ok()) {  // Don't publish a partial batch write
        versions_->SetLastSequence(last_sequence);
      } else {
        HandleMemTableInsertFailure(w.status);
      }
      write_thread_.ExitAsBatchGroupFollower(&w);
    }
    assert(w.state == WriteThread::STATE_COMPLETED);
    // STATE_COMPLETED conditional below handles exit
  }
  if (w.state == WriteThread::STATE_COMPLETED) {
    if (wal_used != nullptr) {
      *wal_used = w.wal_used;
    }
    if (seq_used != nullptr) {
      *seq_used = w.sequence;
    }
    // write is complete and leader has updated sequence
    return w.FinalStatus();
  }
  // else we are the leader of the write batch group
  assert(w.state == WriteThread::STATE_GROUP_LEADER);
  Status status;
  // Once reaches this point, the current writer "w" will try to do its write
  // job.  It may also pick up some of the remaining writers in the "writers_"
  // when it finds suitable, and finish them in the same write batch.
  // This is how a write job could be done by the other writer.
  WriteContext write_context;
  // FIXME: also check disableWAL like others?
  WalContext wal_context(write_options.sync);
  WriteThread::WriteGroup write_group;
  bool in_parallel_group = false;
  uint64_t last_sequence = kMaxSequenceNumber;

  assert(!two_write_queues_ || !disable_memtable);
  {
    // With concurrent writes we do preprocess only in the write thread that
    // also does write to memtable to avoid sync issue on shared data structure
    // with the other thread

    // PreprocessWrite does its own perf timing.
    PERF_TIMER_STOP(write_pre_and_post_process_time);

    status = PreprocessWrite(write_options, &wal_context, &write_context);
    if (!two_write_queues_) {
      // Assign it after ::PreprocessWrite since the sequence might advance
      // inside it by WriteRecoverableState
      last_sequence = versions_->LastSequence();
    }

    PERF_TIMER_START(write_pre_and_post_process_time);
  }

  // Add to log and apply to memtable.  We can release the lock
  // during this phase since &w is currently responsible for logging
  // and protects against concurrent loggers and concurrent writes
  // into memtables

  TEST_SYNC_POINT("DBImpl::WriteImpl:BeforeLeaderEnters");
  last_batch_group_size_ =
      write_thread_.EnterAsBatchGroupLeader(&w, &write_group);
  if (wbwi) {
    assert(write_group.size == 1);
  }

  IOStatus io_s;
  Status pre_release_cb_status;
  size_t seq_inc = 0;
  if (status.ok()) {
    // Rules for when we can update the memtable concurrently
    // 1. supported by memtable
    // 2. Puts are not okay if inplace_update_support
    // 3. Merges are not okay
    //
    // Rules 1..2 are enforced by checking the options
    // during startup (CheckConcurrentWritesSupported), so if
    // options.allow_concurrent_memtable_write is true then they can be
    // assumed to be true.  Rule 3 is checked for each batch.  We could
    // relax rules 2 if we could prevent write batches from referring
    // more than once to a particular key.
    bool parallel = immutable_db_options_.allow_concurrent_memtable_write &&
                    write_group.size > 1;
    size_t total_count = 0;
    size_t valid_batches = 0;
    size_t total_byte_size = 0;
    size_t pre_release_callback_cnt = 0;
    for (auto* writer : write_group) {
      assert(writer);
      if (writer->CheckCallback(this)) {
        valid_batches += writer->batch_cnt;
        if (writer->ShouldWriteToMemtable()) {
          total_count += WriteBatchInternal::Count(writer->batch);
          total_byte_size = WriteBatchInternal::AppendedByteSize(
              total_byte_size, WriteBatchInternal::ByteSize(writer->batch));
          parallel = parallel && !writer->batch->HasMerge();
        }
        if (writer->pre_release_callback) {
          pre_release_callback_cnt++;
        }
      }
    }
    // TODO: this use of operator bool on `tracer_` can avoid unnecessary lock
    // grabs but does not seem thread-safe.
    if (tracer_) {
      InstrumentedMutexLock lock(&trace_mutex_);
      if (tracer_ && tracer_->IsWriteOrderPreserved()) {
        for (auto* writer : write_group) {
          if (writer->CallbackFailed()) {
            continue;
          }
          // TODO: maybe handle the tracing status?
          if (wbwi && !ingest_wbwi_for_commit) {
            // for transaction write, tracer only needs the commit marker which
            // is in writer->batch
            tracer_->Write(wbwi->GetWriteBatch()).PermitUncheckedError();
          } else {
            tracer_->Write(writer->batch).PermitUncheckedError();
          }
        }
      }
    }
    // Note about seq_per_batch_: either disableWAL is set for the entire write
    // group or not. In either case we inc seq for each write batch with no
    // failed callback. This means that there could be a batch with
    // disable_memtable in between; although we do not write this batch to
    // memtable it still consumes a seq. Otherwise, if !seq_per_batch_, we inc
    // the seq per valid written key to mem.
    seq_inc = seq_per_batch_ ? valid_batches : total_count;
    if (wbwi) {
      // Reserve sequence numbers for the ingested memtable. We need to reserve
      // at lease this amount for recovery. During recovery,
      // transactions do not commit by ingesting WBWI. The sequence number
      // associated with the commit entry in WAL is used as the starting
      // sequence number for inserting into memtable. We need to reserve
      // enough sequence numbers here (at least the number of operations
      // in write batch) to assign to memtable entries for this transaction.
      // This prevents updates in different transactions from using out-of-order
      // sequence numbers or the same key+seqno.
      //
      // WBWI ingestion requires not grouping writes, so we don't need to
      // consider incrementing sequence number for WBWI from other writers.
      seq_inc += wbwi->GetWriteBatch()->Count();
    }

    const bool concurrent_update = two_write_queues_;
    // Update stats while we are an exclusive group leader, so we know
    // that nobody else can be writing to these particular stats.
    // We're optimistic, updating the stats before we successfully
    // commit.  That lets us release our leader status early.
    auto stats = default_cf_internal_stats_;
    stats->AddDBStats(InternalStats::kIntStatsNumKeysWritten, total_count,
                      concurrent_update);
    RecordTick(stats_, NUMBER_KEYS_WRITTEN, total_count);
    stats->AddDBStats(InternalStats::kIntStatsBytesWritten, total_byte_size,
                      concurrent_update);
    RecordTick(stats_, BYTES_WRITTEN, total_byte_size);
    stats->AddDBStats(InternalStats::kIntStatsWriteDoneBySelf, 1,
                      concurrent_update);
    RecordTick(stats_, WRITE_DONE_BY_SELF);
    auto write_done_by_other = write_group.size - 1;
    if (write_done_by_other > 0) {
      stats->AddDBStats(InternalStats::kIntStatsWriteDoneByOther,
                        write_done_by_other, concurrent_update);
      RecordTick(stats_, WRITE_DONE_BY_OTHER, write_done_by_other);
    }
    RecordInHistogram(stats_, BYTES_PER_WRITE, total_byte_size);

    if (write_options.disableWAL) {
      has_unpersisted_data_.store(true, std::memory_order_relaxed);
    }

    PERF_TIMER_STOP(write_pre_and_post_process_time);

    if (!two_write_queues_) {
      if (status.ok() && !write_options.disableWAL) {
        assert(wal_context.wal_file_number_size);
        wal_context.prev_size = wal_context.writer->file()->GetFileSize();
        PERF_TIMER_GUARD(write_wal_time);
        io_s = WriteGroupToWAL(write_group, wal_context.writer, wal_used,
                               wal_context.need_wal_sync,
                               wal_context.need_wal_dir_sync, last_sequence + 1,
                               *wal_context.wal_file_number_size);
      }
    } else {
      if (status.ok() && !write_options.disableWAL) {
        PERF_TIMER_GUARD(write_wal_time);
        // LastAllocatedSequence is increased inside WriteToWAL under
        // wal_write_mutex_ to ensure ordered events in WAL
        io_s = ConcurrentWriteGroupToWAL(write_group, wal_used, &last_sequence,
                                         seq_inc);
      } else {
        // Otherwise we inc seq number for memtable writes
        last_sequence = versions_->FetchAddLastAllocatedSequence(seq_inc);
      }
    }
    status = io_s;
    assert(last_sequence != kMaxSequenceNumber);
    const SequenceNumber current_sequence = last_sequence + 1;
    last_sequence += seq_inc;
    // Seqno assigned to this write are [current_sequence, last_sequence]

    if (wal_context.need_wal_sync) {
      VersionEdit synced_wals;
      // Optimize: Only acquire wal_write_mutex_ when needed for sync
      bool need_manifest_update = false;
      wal_write_mutex_.Lock();
      if (status.ok()) {
        MarkLogsSynced(cur_wal_number_, wal_context.need_wal_dir_sync,
                       &synced_wals);
        need_manifest_update = synced_wals.IsWalAddition();
      } else {
        MarkLogsNotSynced(cur_wal_number_);
      }
      wal_write_mutex_.Unlock();
      
      if (need_manifest_update) {
        InstrumentedMutexLock l(&mutex_);
        // TODO: plumb Env::IOActivity, Env::IOPriority
        const ReadOptions read_options;
        status = ApplyWALToManifest(read_options, write_options, &synced_wals);
      }

      // Requesting sync with two_write_queues_ is expected to be very rare. We
      // hence provide a simple implementation that is not necessarily
      // efficient.
      if (status.ok() && two_write_queues_) {
        if (manual_wal_flush_) {
          status = FlushWAL(true);
        } else {
          status = SyncWAL();
        }
      }
    }

    // PreReleaseCallback is called after WAL write and before memtable write
    if (status.ok()) {
      SequenceNumber next_sequence = current_sequence;
      size_t index = 0;
      // Note: the logic for advancing seq here must be consistent with the
      // logic in WriteBatchInternal::InsertInto(write_group...) as well as
      // with WriteBatchInternal::InsertInto(write_batch...) that is called on
      // the merged batch during recovery from the WAL.
      // Optimize: Process callbacks in batches to reduce function call overhead
      for (auto* writer : write_group) {
        if (writer->CallbackFailed()) {
          continue;
        }
        writer->sequence = next_sequence;
        if (writer->pre_release_callback) {
          Status ws = writer->pre_release_callback->Callback(
              writer->sequence, disable_memtable, writer->wal_used, index++,
              pre_release_callback_cnt);
          if (!ws.ok()) {
            status = pre_release_cb_status = ws;
            break;
          }
        }
        // Optimize: Avoid redundant checks by computing increment once
        if (seq_per_batch_) {
          assert(writer->batch_cnt);
          next_sequence += writer->batch_cnt;
        } else if (writer->ShouldWriteToMemtable()) {
          next_sequence += WriteBatchInternal::Count(writer->batch);
        }
      }
    }

    if (status.ok()) {
      PERF_TIMER_FOR_WAIT_GUARD(write_memtable_time);

      if (!parallel) {
        // w.sequence will be set inside InsertInto
        w.status = WriteBatchInternal::InsertInto(
            write_group, current_sequence, column_family_memtables_.get(),
            &flush_scheduler_, &trim_history_scheduler_,
            write_options.ignore_missing_column_families,
            0 /*recovery_log_number*/, this, seq_per_batch_, batch_per_txn_);
      } else {
        write_group.last_sequence = last_sequence;
        write_thread_.LaunchParallelMemTableWriters(&write_group);
        in_parallel_group = true;

        // Each parallel follower is doing each own writes. The leader should
        // also do its own.
        if (w.ShouldWriteToMemtable()) {
          ColumnFamilyMemTablesImpl column_family_memtables(
              versions_->GetColumnFamilySet());
          assert(w.sequence == current_sequence);
          w.status = WriteBatchInternal::InsertInto(
              &w, w.sequence, &column_family_memtables, &flush_scheduler_,
              &trim_history_scheduler_,
              write_options.ignore_missing_column_families, 0 /*log_number*/,
              this, true /*concurrent_memtable_writes*/, seq_per_batch_,
              w.batch_cnt, batch_per_txn_,
              write_options.memtable_insert_hint_per_batch);
        }
      }
      if (seq_used != nullptr) {
        *seq_used = w.sequence;
      }
    }
  }
  PERF_TIMER_START(write_pre_and_post_process_time);

  if (!io_s.ok()) {
    // Check WriteToWAL status
    WALIOStatusCheck(io_s);
  }
  if (!w.CallbackFailed()) {
    if (!io_s.ok()) {
      assert(pre_release_cb_status.ok());
    } else {
      WriteStatusCheck(pre_release_cb_status);
    }
  } else {
    assert(pre_release_cb_status.ok());
  }

  bool should_exit_batch_group = true;
  if (in_parallel_group) {
    // CompleteParallelWorker returns true if this thread should
    // handle exit, false means somebody else did
    should_exit_batch_group = write_thread_.CompleteParallelMemTableWriter(&w);
  }
  if (wbwi && status.ok() && w.status.ok()) {
    uint32_t wbwi_count = wbwi->GetWriteBatch()->Count();
    // skip empty batch case
    if (wbwi_count) {
      // w.batch contains (potentially empty) commit time batch updates,
      // only ingest wbwi if w.batch is applied to memtable successfully
      uint32_t memtable_update_count = w.batch->Count();
      // Seqno assigned to this write are [last_seq + 1 - seq_inc, last_seq].
      // seq_inc includes w.batch (memtable updates) and wbwi
      // w.batch gets first `memtable_update_count` sequence numbers.
      // wbwi gets the rest `wbwi_count` sequence numbers.
      assert(seq_inc == memtable_update_count + wbwi_count);
      assert(wbwi_count > 0);
      assert(last_sequence != kMaxSequenceNumber);
      SequenceNumber lb = last_sequence + 1 - wbwi_count;
      SequenceNumber ub = last_sequence;
      if (two_write_queues_) {
        assert(ub <= versions_->LastAllocatedSequence());
      }
      status =
          IngestWBWIAsMemtable(wbwi, {/*lower_bound=*/lb, /*upper_bound=*/ub},
                               /*min_prep_log=*/log_ref, last_sequence,
                               /*memtable_updated=*/memtable_update_count > 0,
                               write_options.ignore_missing_column_families);
      RecordTick(stats_, NUMBER_WBWI_INGEST);
    }
  }

  if (should_exit_batch_group) {
    if (status.ok()) {
      // Optimize: Process post_memtable_callbacks in a single loop to reduce
      // iteration overhead and improve cache locality
      bool all_callbacks_ok = true;
      for (auto* tmp_w : write_group) {
        assert(tmp_w);
        if (tmp_w->post_memtable_callback) {
          Status tmp_s =
              (*tmp_w->post_memtable_callback)(last_sequence, disable_memtable);
          // TODO: propagate the execution status of post_memtable_callback to
          // caller.
          if (!tmp_s.ok()) {
            all_callbacks_ok = false;
          }
        }
      }
      // Note: if we are to resume after non-OK statuses we need to revisit how
      // we react to non-OK statuses here.
      if (all_callbacks_ok && w.status.ok()) {  // Don't publish a partial batch write
        versions_->SetLastSequence(last_sequence);
      }
    }
    if (!w.status.ok()) {
      if (wal_context.prev_size < SIZE_MAX) {
        InstrumentedMutexLock l(&wal_write_mutex_);
        if (logs_.back().number == wal_context.wal_file_number_size->number) {
          logs_.back().SetAttemptTruncateSize(wal_context.prev_size);
        }
      }
      HandleMemTableInsertFailure(w.status);
    }
    write_thread_.ExitAsBatchGroupLeader(write_group, status);
  }

  if (status.ok()) {
    status = w.FinalStatus();
  }
  return status;
}
// EVOLVE-BLOCK-END
