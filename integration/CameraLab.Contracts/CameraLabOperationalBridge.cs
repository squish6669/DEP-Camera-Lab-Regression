namespace Dep.CameraLab.Contracts;

public sealed record CameraLabOperationalBridgeResultV1(
    bool Accepted,
    string Reason,
    CameraLabScanRecordV1? Record);

/// <summary>
/// Ground-truth-free application boundary for the Camera Lab UI.
/// Accepts only an already-produced inference row, validates its evidence contract,
/// performs the conservative certificate lookup, then creates a persistent scan record.
/// This class does not infer, score, or mutate OCR identity fields.
/// </summary>
public static class CameraLabOperationalBridgeV1
{
    public static CameraLabOperationalBridgeResultV1 Process(
        string recordId,
        CameraLabInferenceV1? inference,
        ICertificateLookupV1? certificateLookup)
    {
        if (inference is null)
            return new CameraLabOperationalBridgeResultV1(false, "INVALID_INFERENCE", null);

        var validation = CameraLabInferenceValidatorV1.Validate(inference);
        if (!validation.Accepted)
            return new CameraLabOperationalBridgeResultV1(false, "INVALID_INFERENCE", null);

        CertificateLookupResultV1 certificate;
        if (certificateLookup is null)
        {
            certificate = new CertificateLookupResultV1("NOT_CHECKED", 0, "", "", "");
        }
        else
        {
            var request = new CertificateLookupRequestV1(
                inference.Serial,
                inference.SerialStatus,
                inference.Image);

            // Enforce lookup eligibility at the application boundary, not only inside a
            // particular lookup implementation. Unapproved or unresolved serial identity
            // must never be sent to any external certificate provider.
            if (!request.IsEligibleForLookup())
            {
                certificate = new CertificateLookupResultV1("REVIEW", 0, "", "", "");
            }
            else
            {
                try
                {
                    certificate = certificateLookup.Lookup(request);
                }
                catch (Exception)
                {
                    // External certificate data is operational input, not OCR ground truth.
                    // A lookup failure must never be converted into a guessed NO_CERT or
                    // allowed to create a persistent record with an actionable conclusion.
                    return new CameraLabOperationalBridgeResultV1(false, "CERTIFICATE_LOOKUP_ERROR", null);
                }
            }
        }

        if (certificate is null || !certificate.IsValid())
            return new CameraLabOperationalBridgeResultV1(false, "INVALID_CERTIFICATE_RESULT", null);

        var created = CameraLabScanRecordPlannerV1.Create(recordId, inference, certificate);
        return created.Accepted
            ? new CameraLabOperationalBridgeResultV1(true, "SCAN_RECORD_READY", created.Record)
            : new CameraLabOperationalBridgeResultV1(false, created.Reason, null);
    }
}
