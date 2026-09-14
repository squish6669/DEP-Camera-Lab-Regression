namespace Dep.CameraLab.Contracts;

public sealed record PendingDestructionBatchPreflightResultV1(
    bool Accepted,
    string Reason);

public static class PendingDestructionBatchPreflightV1
{
    public static PendingDestructionBatchPreflightResultV1 Validate(
        PendingDestructionBatchV1? batch,
        IEnumerable<CameraLabScanRecordV1>? currentRecords)
    {
        if (batch is null || !batch.IsValid())
            return new PendingDestructionBatchPreflightResultV1(false, "INVALID_BATCH");
        if (currentRecords is null)
            return new PendingDestructionBatchPreflightResultV1(false, "NO_CURRENT_RECORDS");

        var records = currentRecords.ToArray();
        if (records.Any(record => record is null))
            return new PendingDestructionBatchPreflightResultV1(false, "INVALID_CURRENT_RECORD");
        if (records.Select(record => record.RecordId).Distinct(StringComparer.Ordinal).Count() != records.Length)
            return new PendingDestructionBatchPreflightResultV1(false, "DUPLICATE_CURRENT_RECORD_ID");

        // Destruction must fail closed if the same production-approved serial identity is present
        // in more than one current scan record, even when only one copy was placed in this batch.
        // This prevents a duplicate scan/history row from making the physical drive identity ambiguous.
        var approvedRecords = records
            .Where(record => string.Equals(record.Inference.SerialStatus, "FOUND", StringComparison.Ordinal))
            .ToArray();
        var approvedSerials = approvedRecords
            .Select(record => CameraLabContractV1.NormalizeSerial(record.Inference.Serial))
            .Where(serial => serial.Length > 0)
            .ToArray();
        if (approvedSerials.Distinct(StringComparer.Ordinal).Count() != approvedSerials.Length)
            return new PendingDestructionBatchPreflightResultV1(false, "DUPLICATE_CURRENT_SERIAL_IDENTITY");

        // A single physical source image must never support more than one current production-approved
        // destruction identity. Distinct serials tied to the same image are contradictory evidence and
        // require review rather than allowing either record to advance to destruction.
        var approvedImages = approvedRecords
            .Select(record => record.Inference.Image?.Trim() ?? string.Empty)
            .Where(image => image.Length > 0)
            .ToArray();
        if (approvedImages.Distinct(StringComparer.Ordinal).Count() != approvedImages.Length)
            return new PendingDestructionBatchPreflightResultV1(false, "DUPLICATE_CURRENT_IMAGE_IDENTITY");

        var byId = records.ToDictionary(record => record.RecordId, StringComparer.Ordinal);
        foreach (var entry in batch.Entries)
        {
            if (!byId.TryGetValue(entry.RecordId, out var record))
                return new PendingDestructionBatchPreflightResultV1(false, "BATCH_RECORD_MISSING");
            if (!record.IsValid())
                return new PendingDestructionBatchPreflightResultV1(false, "CURRENT_RECORD_INVALID");
            if (!string.Equals(record.Certificate.LookupStatus, "NO_CERT", StringComparison.Ordinal))
                return new PendingDestructionBatchPreflightResultV1(false, "CERTIFICATE_STATE_CHANGED");
            if (!string.Equals(record.DestructionStatus, "PENDING_DESTRUCTION", StringComparison.Ordinal) ||
                !string.Equals(record.PendingDestructionBin, batch.Bin, StringComparison.Ordinal))
                return new PendingDestructionBatchPreflightResultV1(false, "PENDING_DESTRUCTION_STATE_CHANGED");
            if (!string.Equals(record.Inference.SerialStatus, "FOUND", StringComparison.Ordinal))
                return new PendingDestructionBatchPreflightResultV1(false, "SERIAL_NOT_PRODUCTION_APPROVED");
            if (!string.Equals(CameraLabContractV1.NormalizeSerial(record.Inference.Serial),
                               CameraLabContractV1.NormalizeSerial(entry.Serial),
                               StringComparison.Ordinal))
                return new PendingDestructionBatchPreflightResultV1(false, "SERIAL_IDENTITY_CHANGED");
            if (!string.Equals(record.Inference.Image, entry.Image, StringComparison.Ordinal))
                return new PendingDestructionBatchPreflightResultV1(false, "IMAGE_IDENTITY_CHANGED");
        }

        return new PendingDestructionBatchPreflightResultV1(true, "READY_FOR_DESTRUCTION");
    }
}
