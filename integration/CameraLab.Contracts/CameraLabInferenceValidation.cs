namespace Dep.CameraLab.Contracts;

public sealed record CameraLabInferenceValidationResultV1(bool Accepted, string Reason);

public static class CameraLabInferenceValidatorV1
{
    private static readonly IReadOnlySet<string> AllowedSerialStatuses =
        new HashSet<string>(StringComparer.Ordinal) { "FOUND", "REVIEW" };

    private static readonly IReadOnlySet<string> AllowedModelStatuses =
        new HashSet<string>(StringComparer.Ordinal) { "FOUND", "REVIEW" };

    private static readonly IReadOnlySet<string> AllowedCapacityStatuses =
        new HashSet<string>(StringComparer.Ordinal) { "READY", "CONFIRM", "REVIEW" };

    public static CameraLabInferenceValidationResultV1 Validate(CameraLabInferenceV1? inference)
    {
        if (inference is null)
            return new CameraLabInferenceValidationResultV1(false, "INFERENCE_MISSING");

        if (string.IsNullOrWhiteSpace(inference.Image))
            return new CameraLabInferenceValidationResultV1(false, "IMAGE_MISSING");

        if (!AllowedSerialStatuses.Contains(inference.SerialStatus))
            return new CameraLabInferenceValidationResultV1(false, "INVALID_SERIAL_STATUS");

        if (!AllowedModelStatuses.Contains(inference.ModelStatus))
            return new CameraLabInferenceValidationResultV1(false, "INVALID_MODEL_STATUS");

        if (!AllowedCapacityStatuses.Contains(inference.CapacityStatus))
            return new CameraLabInferenceValidationResultV1(false, "INVALID_CAPACITY_STATUS");

        if (!double.IsFinite(inference.SerialScore) || !double.IsFinite(inference.CapacityConfidence))
            return new CameraLabInferenceValidationResultV1(false, "NONFINITE_SCORE");

        if (string.Equals(inference.SerialStatus, "FOUND", StringComparison.Ordinal))
        {
            if (CameraLabContractV1.NormalizeSerial(inference.Serial).Length == 0)
                return new CameraLabInferenceValidationResultV1(false, "FOUND_SERIAL_MISSING");
            if (string.IsNullOrWhiteSpace(inference.SerialEvidence))
                return new CameraLabInferenceValidationResultV1(false, "FOUND_SERIAL_EVIDENCE_MISSING");
        }

        if (string.Equals(inference.ModelStatus, "FOUND", StringComparison.Ordinal))
        {
            if (string.IsNullOrWhiteSpace(inference.Model))
                return new CameraLabInferenceValidationResultV1(false, "FOUND_MODEL_MISSING");
            if (string.IsNullOrWhiteSpace(inference.ModelEvidence))
                return new CameraLabInferenceValidationResultV1(false, "FOUND_MODEL_EVIDENCE_MISSING");
        }

        if (!string.IsNullOrWhiteSpace(inference.Manufacturer) &&
            string.IsNullOrWhiteSpace(inference.ManufacturerEvidence))
            return new CameraLabInferenceValidationResultV1(false, "MANUFACTURER_EVIDENCE_MISSING");

        if (!string.Equals(inference.CapacityStatus, "REVIEW", StringComparison.Ordinal))
        {
            if (string.IsNullOrWhiteSpace(inference.Capacity))
                return new CameraLabInferenceValidationResultV1(false, "CAPACITY_VALUE_MISSING");
            if (string.IsNullOrWhiteSpace(inference.CapacityEvidence))
                return new CameraLabInferenceValidationResultV1(false, "CAPACITY_EVIDENCE_MISSING");
        }

        if (string.IsNullOrWhiteSpace(inference.Capacity) &&
            !string.Equals(inference.CapacityStatus, "REVIEW", StringComparison.Ordinal))
            return new CameraLabInferenceValidationResultV1(false, "MISSING_CAPACITY_NOT_REVIEW");

        return new CameraLabInferenceValidationResultV1(true, "INFERENCE_CONTRACT_VALID");
    }
}
