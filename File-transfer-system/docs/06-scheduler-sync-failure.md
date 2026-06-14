# 7. Async Algorithm Explanation

## Scheduler System

Use APScheduler inside the monolithic Flask backend for the first version.

Supported jobs:

- One-time transfer: store `scheduled_at`.
- Recurring sync: store `schedule_cron` and `timezone`.
- Real-time sync: triggered by agent file events.

Timezone rules:

- Store all execution timestamps in UTC.
- Store user-selected timezone on `sync_rules.timezone`.
- Convert cron schedules from local timezone to UTC execution windows.
- Display all timestamps in the user timezone on the dashboard.

## Queue-Based Execution

Even in a monolith, separate job creation from job execution:

```text
scheduler tick
  -> find due schedules
  -> create transfer_jobs rows
  -> agents poll and claim jobs
  -> backend marks job assigned using transaction
```

Use transaction-safe claiming:

```sql
UPDATE transfer_jobs
SET status = 'assigned', assigned_agent_id = ?, updated_at = UTC_TIMESTAMP()
WHERE id = ?
  AND status = 'queued';
```

If affected rows = 1, the agent owns the job. If 0, another worker already claimed it.

## File Synchronization Logic

Manifest fields:

- Relative path
- Size
- Modified time in UTC
- SHA-256 checksum
- Is deleted
- File ID or inode where available

Comparison logic:

```text
for each relative_path in union(left_manifest, right_manifest):
  if exists only on left:
    copy left -> right
  if exists only on right:
    copy right -> left
  if exists on both and checksum same:
    no-op
  if exists on both and checksum differs:
    if one side modified after last sync:
      copy newer side to older side
    if both sides modified after last sync:
      apply conflict policy
```

## Avoid Duplication

- Use `(server_id, relative_path)` unique key.
- Use checksum comparison before copying.
- For bulk sync, transfer only changed files.
- Use temp filenames like `.filename.job_uuid.tmp`.
- Final rename should be atomic on the same filesystem.

## Conflict Handling

Last-write-wins:

- Compare normalized UTC modified time.
- Newer file overwrites older file.
- Save overwritten file as a version first.

Versioning:

- Keep both files.
- Rename losing file to `filename.conflict.<server>.<timestamp>`.
- Insert record into `file_versions`.
- Insert conflict event in `job_events`.

Manual:

- Mark job as `conflict`.
- Show conflict in dashboard.
- Admin chooses left, right, or keep both.

# 8. Failure & Retry Handling

## Retry Policy

- Retry transient failures: network timeout, agent offline, temporary file lock, SSH connection reset.
- Do not retry permanent failures blindly: permission denied, invalid path, missing credential, checksum mismatch after repeated copy.

Recommended backoff:

```text
retry 1: 30 seconds
retry 2: 2 minutes
retry 3: 10 minutes
then mark failed and alert
```

## Resume Large Transfers

- Use `rsync --partial` on Linux.
- Use chunked copy on Windows for large files.
- Store progress in `transfer_jobs.transferred_bytes`.
- Verify final checksum before marking success.

## Failure States

- Agent offline: return job to queue if not started, mark retrying if running.
- Backend restart: jobs in running state older than heartbeat timeout become retrying.
- Destination full: fail job, create critical alert.
- Checksum mismatch: retry once from clean temp file, then fail.
- Source changed during copy: recalculate checksum and restart if policy requires consistency.

