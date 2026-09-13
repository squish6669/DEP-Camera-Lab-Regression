namespace Dep.CameraLab.Contracts;

public sealed record PendingDestructionRecordTransitionResultV1(
    bool Accepted,
    string Reason,
    CameraLabScanRecordV1? Record);

public static class PendingDestructionRecordTransitionV1
{
    public static PendingDestructionRecordTransitionResultV1 Assign(
        CameraLabScanRecordV1? record,
        string bin)
    {
        if (record is null || !record.IsValid())
            return new PendingDestructionRecordTransitionResultV1(false, "INVALID_SCAN_RECORD", null);

        if (!string.Equals(record.Certificate.LookupStatus, "NO_CERT", StringComparison.Ordinal))
            return new PendingDestructionRecordTransitionResultV1(false, "CERTIFICATE_STATUS_NOT_NO_CERT", null);

        if (!string.Equals(record.Inference.SerialStatus, "FOUND", StringComparison.Ordinal) ||
            CameraLabContractV1.NormalizeSerial(record.Inference.Serial).Length == 0)
            return new PendingDestructionRecordTransitionResultV1(false, "SERIAL_NOT_PRODUCTION_APPROVED", null);

        if (!CameraLabContractV1.IsAllowedDestructionBin(bin))
            return new PendingDestructionRecordTransitionResultV1(false, "INVALID_DESTRUCTION_BIN", null);

        if (!string.IsNullOrWhiteSpace(record.PendingDestructionBin) ||
            !string.IsNullOrWhiteSpace(record.DestructionStatus))
            return new PendingDestructionRecordTransitionResultV1(false, "ALREADY_ASSIGNED", null);

        var updated = record with
        {
            PendingDestructionBin = bin.Trim().ToUpperInvariant(),
            DestructionStatus = "PENDING_DESTRUCTION"
        };

        return updated.IsValid()
            ? new PendingDestructionRecordTransitionResultV1(true, "ASSIGNED_PENDING_DESTRUCTION", updated)
            : new PendingDestructionRecordTransitionResultV1(false, "INVALID_TRANSITION", null);
    }
}
