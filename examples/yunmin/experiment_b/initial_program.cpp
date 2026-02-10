// EVOLVE-BLOCK-START
IOStatus DBImpl::WriteToWAL(const WriteBatch& merged_batch,
                            const WriteOptions& write_options,
                            log::Writer* log_writer, uint64_t* wal_used,
                            uint64_t* log_size,
                            WalFileNumberSize& wal_file_number_size,
                            SequenceNumber sequence) {
  assert(log_size != nullptr);

  Slice log_entry = WriteBatchInternal::Contents(&merged_batch);
  TEST_SYNC_POINT_CALLBACK("DBImpl::WriteToWAL:log_entry", &log_entry);
  auto s = merged_batch.VerifyChecksum();
  if (!s.ok()) {
    return status_to_io_status(std::move(s));
  }
  *log_size = log_entry.size();
  // When two_write_queues_ WriteToWAL has to be protected from concurretn calls
  // from the two queues anyway and wal_write_mutex_ is already held. Otherwise
  // if manual_wal_flush_ is enabled we need to protect log_writer->AddRecord
  // from possible concurrent calls via the FlushWAL by the application.
  const bool needs_locking = manual_wal_flush_ && !two_write_queues_;
  // Due to performance cocerns of missed branch prediction penalize the new
  // manual_wal_flush_ feature (by UNLIKELY) instead of the more common case
  // when we do not need any locking.
  if (UNLIKELY(needs_locking)) {
    wal_write_mutex_.Lock();
  }
  IOStatus io_s = log_writer->MaybeAddUserDefinedTimestampSizeRecord(
      write_options, versions_->GetColumnFamiliesTimestampSizeForRecord());
  if (!io_s.ok()) {
    return io_s;
  }
  io_s = log_writer->AddRecord(write_options, log_entry, sequence);

  if (UNLIKELY(needs_locking)) {
    wal_write_mutex_.Unlock();
  }
  if (wal_used != nullptr) {
    *wal_used = cur_wal_number_;
    assert(*wal_used == wal_file_number_size.number);
  }
  wals_total_size_.FetchAddRelaxed(log_entry.size());
  wal_file_number_size.AddSize(*log_size);
  wal_empty_ = false;

  return io_s;
}
// EVOLVE-BLOCK-END
