// EVOLVE-BLOCK-START
void CompactionJob::ProcessKeyValueCompaction(SubcompactionState* sub_compact) {
  TEST_SYNC_POINT("CompactionJob::ProcessKeyValueCompaction:Start");
  assert(sub_compact);
  assert(sub_compact->compaction);

  if (!ShouldUseLocalCompaction(sub_compact)) {
    return;
  }

  AutoThreadOperationStageUpdater stage_updater(
      ThreadStatus::STAGE_COMPACTION_PROCESS_KV);

  const uint64_t start_cpu_micros = db_options_.clock->CPUMicros();
  uint64_t prev_cpu_micros = start_cpu_micros;
  const CompactionIOStatsSnapshot io_stats = InitializeIOStats();
  ColumnFamilyData* cfd = sub_compact->compaction->column_family_data();
  const CompactionFilter* compaction_filter;
  std::unique_ptr<CompactionFilter> compaction_filter_from_factory = nullptr;
  Status filter_status = SetupAndValidateCompactionFilter(
      sub_compact, cfd->ioptions().compaction_filter, compaction_filter,
      compaction_filter_from_factory);
  if (!filter_status.ok()) {
    sub_compact->status = filter_status;
    return;
  }

  NotifyOnSubcompactionBegin(sub_compact);

  SubcompactionKeyBoundaries boundaries(sub_compact->start, sub_compact->end);
  SubcompactionInternalIterators iterators;
  ReadOptions read_options;
  const WriteOptions write_options(Env::IOPriority::IO_LOW,
                                   Env::IOActivity::kCompaction);

  InternalIterator* input_iter = CreateInputIterator(
      sub_compact, cfd, iterators, boundaries, read_options);

  assert(input_iter);

  Status status =
      MaybeResumeSubcompactionProgressOnInputIterator(sub_compact, input_iter);

  if (status.IsNotFound()) {
    input_iter->SeekToFirst();
  } else if (!status.ok()) {
    sub_compact->status = status;
    return;
  }

  MergeHelper merge(
      env_, cfd->user_comparator(), cfd->ioptions().merge_operator.get(),
      compaction_filter, db_options_.info_log.get(),
      false /* internal key corruption is expected */,
      job_context_->GetLatestSnapshotSequence(), job_context_->snapshot_checker,
      compact_->compaction->level(), db_options_.stats);
  std::unique_ptr<BlobFileBuilder> blob_file_builder;

  auto c_iter =
      CreateCompactionIterator(sub_compact, cfd, input_iter, compaction_filter,
                               merge, blob_file_builder, write_options);
  assert(c_iter);
  c_iter->SeekToFirst();

  TEST_SYNC_POINT("CompactionJob::Run():Inprogress");
  TEST_SYNC_POINT_CALLBACK("CompactionJob::Run():PausingManualCompaction:1",
                           static_cast<void*>(const_cast<std::atomic<bool>*>(
                               &manual_compaction_canceled_)));

  auto [open_file_func, close_file_func] =
      CreateFileHandlers(sub_compact, boundaries);

  status = ProcessKeyValue(sub_compact, cfd, c_iter.get(), open_file_func,
                           close_file_func, prev_cpu_micros);

  status = FinalizeProcessKeyValueStatus(cfd, input_iter, c_iter.get(), status);

  FinalizeSubcompaction(sub_compact, status, open_file_func, close_file_func,
                        blob_file_builder.get(), c_iter.get(), input_iter,
                        start_cpu_micros, prev_cpu_micros, io_stats);

  NotifyOnSubcompactionCompleted(sub_compact);
}
// EVOLVE-BLOCK-END
