namespace Dep.CameraLab.Contracts;

public sealed record CertificateReconciliationResultV1(
    bool Accepted,
    string Reason,
    CameraLabScanRecordV1? Record);

public static class CertificateReconciliationPlannerV1
{
    public static CertificateReconciliationResultV1 RefreshFromLookup(
        CameraLabScanRecordV1? existing,
        ICertificateLookupV1? lookup)
    {
        if (existing is null || lookup is null)
            return new CertificateReconciliationResultV1(false, "INVALID_INPUT", null);

        if (!existing.IsValid())
            return new CertificateReconciliationResultV1(false, "INVALID_EXISTING_RECORD", null);

        if (!string.Equals(existing.Inference.SerialStatus, "FOUND", StringComparison.Ordinal) ||
            CameraLabContractV1.NormalizeSerial(existing.Inference.Serial).Length == 0)
            return new CertificateReconciliationResultV1(false, "SERIAL_NOT_PRODUCTION_APPROVED", null);

        var request = new CertificateLookupRequestV1(
            existing.Inference.Serial,
            existing.Inference.SerialStatus,
            existing.Inference.Image);

        if (!request.IsEligibleForLookup())
            return new CertificateReconciliationResultV1(false, "SERIAL_NOT_PRODUCTION_APPROVED", null);

        var refreshedCertificate = lookup.Lookup(request);
        return ApplySerialBoundLookupResult(existing, refreshedCertificate);
    }

    public static CertificateReconciliationResultV1 Reconcile(
        CameraLabScanRecordV1? existing,
        CertificateLookupResultV1? refreshedCertificate)
    {
        if (existing is null || refreshedCertificate is null)
            return new CertificateReconciliationResultV1(false, "INVALID_INPUT", null);

        if (!existing.IsValid())
            return new CertificateReconciliationResultV1(false, "INVALID_EXISTING_RECORD", null);

        if (!refreshedCertificate.IsValid())
            return new CertificateReconciliationResultV1(false, "INVALID_CERTIFICATE_RESULT", null);

        if (!string.Equals(existing.Inference.SerialStatus, "FOUND", StringComparison.Ordinal) ||
            CameraLabContractV1.NormalizeSerial(existing.Inference.Serial).Length == 0)
            return new CertificateReconciliationResultV1(false, "SERIAL_NOT_PRODUCTION_APPROVED", null);

        if (string.Equals(refreshedCertificate.LookupStatus, "CERT_FOUND", StringComparison.Ordinal))
            return new CertificateReconciliationResultV1(false, "CERTIFICATE_RESULT_NOT_SERIAL_BOUND", null);

        return ApplyNonFoundResult(existing, refreshedCertificate);
    }

    private static CertificateReconciliationResultV1 ApplySerialBoundLookupResult(
        CameraLabScanRecordV1 existing,
        CertificateLookupResultV1? refreshedCertificate)
    {
        if (refreshedCertificate is null || !refreshedCertificate.IsValid())
            return new CertificateReconciliationResultV1(false, "INVALID_CERTIFICATE_RESULT", null);

        if (!string.Equals(refreshedCertificate.LookupStatus, "CERT_FOUND", StringComparison.Ordinal))
            return ApplyNonFoundResult(existing, refreshedCertificate);

        // CERT_FOUND is actionable only on this private path, immediately after a lookup that
        // was issued from the existing record's own production-approved serial. This prevents
        // callers from clearing pending destruction with an otherwise valid certificate result
        // that cannot prove which serial was queried.
        var reconciled = existing with
        {
            Certificate = refreshedCertificate,
            PendingDestructionBin = string.Empty,
            DestructionStatus = string.Empty
        };

        return reconciled.IsValid()
            ? new CertificateReconciliationResultV1(true, "CERT_FOUND_REMOVED_FROM_PENDING_DESTRUCTION", reconciled)
            : new CertificateReconciliationResultV1(false, "INVALID_RECONCILED_RECORD", null);
    }

    private static CertificateReconciliationResultV1 ApplyNonFoundResult(
        CameraLabScanRecordV1 existing,
        CertificateLookupResultV1 refreshedCertificate)
    {
        if (string.Equals(refreshedCertificate.LookupStatus, "REVIEW", StringComparison.Ordinal) ||
            string.Equals(refreshedCertificate.LookupStatus, "NOT_CHECKED", StringComparison.Ordinal))
            return new CertificateReconciliationResultV1(false, "CERTIFICATE_RESULT_NOT_ACTIONABLE", null);

        if (string.Equals(refreshedCertificate.LookupStatus, "NO_CERT", StringComparison.Ordinal))
        {
            var unchanged = existing with { Certificate = refreshedCertificate };
            return unchanged.IsValid()
                ? new CertificateReconciliationResultV1(true, "NO_CERT_CONFIRMED", unchanged)
                : new CertificateReconciliationResultV1(false, "INVALID_RECONCILED_RECORD", null);
        }

        return new CertificateReconciliationResultV1(false, "UNSUPPORTED_CERTIFICATE_STATUS", null);
    }
}
