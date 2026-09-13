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
