namespace Dep.CameraLab.Contracts;

public sealed record CameraLabScanRecordCreationResultV1(
    bool Accepted,
    string Reason,
    CameraLabScanRecordV1? Record);

public static class CameraLabScanRecordPlannerV1
{
    public static CameraLabScanRecordCreationResultV1 Create(
        string recordId,
        CameraLabInferenceV1? inference,
        CertificateLookupResultV1? certificate)
    {
        if (string.IsNullOrWhiteSpace(recordId))
            return new CameraLabScanRecordCreationResultV1(false, "INVALID_RECORD_ID", null);
        if (inference is null || certificate is null)
            return new CameraLabScanRecordCreationResultV1(false, "INVALID_INPUT", null);
        if (string.IsNullOrWhiteSpace(inference.Image))
            return new CameraLabScanRecordCreationResultV1(false, "INVALID_IMAGE", null);
        if (!certificate.IsValid())
            return new CameraLabScanRecordCreationResultV1(false, "INVALID_CERTIFICATE_RESULT", null);

        var serialApproved =
            string.Equals(inference.SerialStatus, "FOUND", StringComparison.Ordinal) &&
            CameraLabContractV1.NormalizeSerial(inference.Serial).Length > 0;

        // Actionable certificate conclusions are permitted only for a production-approved
        // serial. REVIEW and NOT_CHECKED remain persistable as non-actionable records.
        if ((string.Equals(certificate.LookupStatus, "CERT_FOUND", StringComparison.Ordinal) ||
             string.Equals(certificate.LookupStatus, "NO_CERT", StringComparison.Ordinal)) &&
            !serialApproved)
            return new CameraLabScanRecordCreationResultV1(false, "SERIAL_NOT_PRODUCTION_APPROVED", null);

        var record = new CameraLabScanRecordV1(
            recordId.Trim(),
            inference,
            certificate,
            string.Empty,
            string.Empty);

        return record.IsValid()
            ? new CameraLabScanRecordCreationResultV1(true, "RECORD_CREATED", record)
            : new CameraLabScanRecordCreationResultV1(false, "INVALID_SCAN_RECORD", null);
    }
}
