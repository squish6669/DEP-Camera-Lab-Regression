using System.Text.Json.Serialization;

namespace Dep.CameraLab.Contracts;

public static class CameraLabContractV1
{
    public const string Version = "1.0";
    public static readonly IReadOnlySet<string> AllowedLookupStatuses =
        new HashSet<string>(StringComparer.Ordinal) { "NOT_CHECKED", "NO_CERT", "CERT_FOUND", "REVIEW" };
    public static readonly IReadOnlySet<string> AllowedDestructionBins =
        new HashSet<string>(Enumerable.Range(1, 12).Select(i => $"DS-{i:00}"), StringComparer.Ordinal);

    public static bool IsAllowedDestructionBin(string? value) =>
        !string.IsNullOrWhiteSpace(value) && AllowedDestructionBins.Contains(value.Trim().ToUpperInvariant());

    public static string NormalizeSerial(string? value) =>
        string.IsNullOrWhiteSpace(value)
            ? string.Empty
            : new string(value.Where(char.IsLetterOrDigit).Select(char.ToUpperInvariant).ToArray());
}

public sealed record CameraLabInferenceV1(
    [property: JsonPropertyName("Image")] string Image,
    [property: JsonPropertyName("Manufacturer")] string Manufacturer,
    [property: JsonPropertyName("ManufacturerEvidence")] string ManufacturerEvidence,
    [property: JsonPropertyName("Serial")] string Serial,
    [property: JsonPropertyName("SerialScore")] double SerialScore,
    [property: JsonPropertyName("SerialStatus")] string SerialStatus,
    [property: JsonPropertyName("SerialEvidence")] string SerialEvidence,
    [property: JsonPropertyName("SerialTopCandidates")] string SerialTopCandidates,
    [property: JsonPropertyName("Model")] string Model,
    [property: JsonPropertyName("ModelStatus")] string ModelStatus,
    [property: JsonPropertyName("ModelEvidence")] string ModelEvidence,
    [property: JsonPropertyName("Capacity")] string Capacity,
    [property: JsonPropertyName("CapacityGB")] object? CapacityGB,
    [property: JsonPropertyName("CapacityConfidence")] double CapacityConfidence,
    [property: JsonPropertyName("CapacityStatus")] string CapacityStatus,
    [property: JsonPropertyName("CapacityEvidence")] string CapacityEvidence);

public sealed record CertificateLookupRequestV1(
    string Serial,
    string SerialStatus,
    string Image)
{
    public bool IsEligibleForLookup() =>
        !string.IsNullOrWhiteSpace(Serial) &&
        string.Equals(SerialStatus, "FOUND", StringComparison.Ordinal);
}

public interface ICertificateLookupV1
{
    CertificateLookupResultV1 Lookup(CertificateLookupRequestV1 request);
}

public sealed record CertificateIndexRecordV1(string Serial, string CertId, string CertPath);

public sealed class ExactSerialCertificateLookupV1 : ICertificateLookupV1
{
    private readonly IReadOnlyList<CertificateIndexRecordV1>? _records;

    public ExactSerialCertificateLookupV1(IEnumerable<CertificateIndexRecordV1>? records)
    {
        _records = records?.ToArray();
    }

    public CertificateLookupResultV1 Lookup(CertificateLookupRequestV1 request)
    {
        if (!request.IsEligibleForLookup())
            return new CertificateLookupResultV1("REVIEW", 0, "", "", "");

        if (_records is null)
            return new CertificateLookupResultV1("NOT_CHECKED", 0, "", "", "");

        var normalized = CameraLabContractV1.NormalizeSerial(request.Serial);
        if (normalized.Length == 0)
            return new CertificateLookupResultV1("REVIEW", 0, "", "", "");

        var matches = _records
            .Where(record => CameraLabContractV1.NormalizeSerial(record.Serial) == normalized)
            .ToArray();

        if (matches.Length == 0)
            return new CertificateLookupResultV1("NO_CERT", 0, "", "", "");

        if (matches.Length != 1)
            return new CertificateLookupResultV1("REVIEW", matches.Length, "", "", "");

        var match = matches[0];
        return new CertificateLookupResultV1(
            "CERT_FOUND",
            1,
            match.CertId ?? "",
            match.CertPath ?? "",
            "EXACT_NORMALIZED_SERIAL");
    }
}

public sealed record CertificateLookupResultV1(
    string LookupStatus,
    int CertMatchCount,
    string CertId,
    string CertPath,
    string CertMatchMethod)
{
    public bool IsValid()
    {
        if (!CameraLabContractV1.AllowedLookupStatuses.Contains(LookupStatus)) return false;
        if (CertMatchCount < 0) return false;
        if (LookupStatus == "CERT_FOUND")
            return CertMatchCount == 1 && CertMatchMethod == "EXACT_NORMALIZED_SERIAL";
        return string.IsNullOrEmpty(CertMatchMethod) && string.IsNullOrEmpty(CertId) && string.IsNullOrEmpty(CertPath);
    }
}

public sealed record PendingDestructionAssignmentV1(string Image, string Serial, string Bin)
{
    public bool IsValid() =>
        !string.IsNullOrWhiteSpace(Image) &&
        !string.IsNullOrWhiteSpace(Serial) &&
        CameraLabContractV1.IsAllowedDestructionBin(Bin);
}

public sealed record PendingDestructionAssignmentRequestV1(
    CameraLabInferenceV1 Inference,
    CertificateLookupResultV1 Certificate,
    string Bin);

public sealed record PendingDestructionAssignmentDecisionV1(
    bool Accepted,
    string Reason,
    PendingDestructionAssignmentV1? Assignment);

public static class PendingDestructionPlannerV1
{
    public static PendingDestructionAssignmentDecisionV1 Evaluate(PendingDestructionAssignmentRequestV1 request)
    {
        if (request.Inference is null || request.Certificate is null)
            return new PendingDestructionAssignmentDecisionV1(false, "INVALID_INPUT", null);

        if (!string.Equals(request.Inference.SerialStatus, "FOUND", StringComparison.Ordinal) ||
            string.IsNullOrWhiteSpace(request.Inference.Serial))
            return new PendingDestructionAssignmentDecisionV1(false, "SERIAL_NOT_PRODUCTION_APPROVED", null);

        if (!request.Certificate.IsValid())
            return new PendingDestructionAssignmentDecisionV1(false, "INVALID_CERTIFICATE_RESULT", null);

        if (!string.Equals(request.Certificate.LookupStatus, "NO_CERT", StringComparison.Ordinal))
            return new PendingDestructionAssignmentDecisionV1(false, "CERTIFICATE_STATUS_NOT_NO_CERT", null);

        if (!CameraLabContractV1.IsAllowedDestructionBin(request.Bin))
            return new PendingDestructionAssignmentDecisionV1(false, "INVALID_DESTRUCTION_BIN", null);

        var assignment = new PendingDestructionAssignmentV1(
            request.Inference.Image,
            request.Inference.Serial,
            request.Bin.Trim().ToUpperInvariant());

        return assignment.IsValid()
            ? new PendingDestructionAssignmentDecisionV1(true, "ASSIGNED_PENDING_DESTRUCTION", assignment)
            : new PendingDestructionAssignmentDecisionV1(false, "INVALID_ASSIGNMENT", null);
    }
}

public sealed record CameraLabScanRecordV1(
    string RecordId,
    CameraLabInferenceV1 Inference,
    CertificateLookupResultV1 Certificate,
    string PendingDestructionBin,
    string DestructionStatus)
{
    public bool IsValid()
    {
        if (string.IsNullOrWhiteSpace(RecordId) || string.IsNullOrWhiteSpace(Inference.Image)) return false;
        if (!Certificate.IsValid()) return false;
        if (string.IsNullOrWhiteSpace(PendingDestructionBin)) return string.IsNullOrWhiteSpace(DestructionStatus);
        return Certificate.LookupStatus == "NO_CERT" &&
               CameraLabContractV1.IsAllowedDestructionBin(PendingDestructionBin) &&
               DestructionStatus == "PENDING_DESTRUCTION";
    }
}

public sealed record PendingDestructionBatchEntryV1(string RecordId, string Image, string Serial)
{
    public bool IsValid() =>
        !string.IsNullOrWhiteSpace(RecordId) &&
        !string.IsNullOrWhiteSpace(Image) &&
        CameraLabContractV1.NormalizeSerial(Serial).Length > 0;
}

public sealed record PendingDestructionBatchV1(
    string BatchId,
    string Bin,
    IReadOnlyList<PendingDestructionBatchEntryV1> Entries)
{
    public bool IsValid()
    {
        if (string.IsNullOrWhiteSpace(BatchId) || !CameraLabContractV1.IsAllowedDestructionBin(Bin)) return false;
        if (Entries is null || Entries.Count == 0 || Entries.Any(entry => entry is null || !entry.IsValid())) return false;
        if (Entries.Select(entry => entry.RecordId).Distinct(StringComparer.Ordinal).Count() != Entries.Count) return false;
        return Entries.Select(entry => CameraLabContractV1.NormalizeSerial(entry.Serial))
            .Distinct(StringComparer.Ordinal).Count() == Entries.Count;
    }
}

public sealed record PendingDestructionBatchBuildResultV1(
    bool Accepted,
    string Reason,
    PendingDestructionBatchV1? Batch);

public static class PendingDestructionBatchPlannerV1
{
    public static PendingDestructionBatchBuildResultV1 Build(
        string BatchId,
        string Bin,
        IEnumerable<CameraLabScanRecordV1>? records)
    {
        if (string.IsNullOrWhiteSpace(BatchId))
            return new PendingDestructionBatchBuildResultV1(false, "INVALID_BATCH_ID", null);
        if (!CameraLabContractV1.IsAllowedDestructionBin(Bin))
            return new PendingDestructionBatchBuildResultV1(false, "INVALID_DESTRUCTION_BIN", null);
        if (records is null)
            return new PendingDestructionBatchBuildResultV1(false, "NO_RECORDS", null);

        var canonicalBin = Bin.Trim().ToUpperInvariant();
        var source = records.ToArray();
        if (source.Length == 0)
            return new PendingDestructionBatchBuildResultV1(false, "NO_RECORDS", null);
        if (source.Any(record => record is null || !record.IsValid()))
            return new PendingDestructionBatchBuildResultV1(false, "INVALID_SCAN_RECORD", null);
        if (source.Any(record => !string.Equals(record.PendingDestructionBin, canonicalBin, StringComparison.Ordinal)))
            return new PendingDestructionBatchBuildResultV1(false, "CROSS_BIN_RECORD", null);
        if (source.Select(record => record.RecordId).Distinct(StringComparer.Ordinal).Count() != source.Length)
            return new PendingDestructionBatchBuildResultV1(false, "DUPLICATE_RECORD_ID", null);

        var normalizedSerials = source.Select(record => CameraLabContractV1.NormalizeSerial(record.Inference.Serial)).ToArray();
        if (normalizedSerials.Any(serial => serial.Length == 0) ||
            normalizedSerials.Distinct(StringComparer.Ordinal).Count() != source.Length)
            return new PendingDestructionBatchBuildResultV1(false, "DUPLICATE_OR_INVALID_SERIAL", null);

        var entries = source
            .Select(record => new PendingDestructionBatchEntryV1(record.RecordId, record.Inference.Image, record.Inference.Serial))
            .ToArray();
        var batch = new PendingDestructionBatchV1(BatchId.Trim(), canonicalBin, entries);

        return batch.IsValid()
            ? new PendingDestructionBatchBuildResultV1(true, "BATCH_READY", batch)
            : new PendingDestructionBatchBuildResultV1(false, "INVALID_BATCH", null);
    }
}
