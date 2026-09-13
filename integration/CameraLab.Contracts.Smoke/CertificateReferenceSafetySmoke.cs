using System.Runtime.CompilerServices;
using Dep.CameraLab.Contracts;

internal static class CertificateReferenceSafetySmoke
{
    [ModuleInitializer]
    internal static void Run()
    {
        var request = new CertificateLookupRequestV1("SERIAL1", "FOUND", "certificate-reference-smoke");
        var incompleteLookup = new ExactSerialCertificateLookupV1(new[]
        {
            new CertificateIndexRecordV1("SER-IAL1", "", "")
        });

        var incomplete = incompleteLookup.Lookup(request);
        if (incomplete.LookupStatus != "REVIEW" || incomplete.CertMatchCount != 1 || !incomplete.IsValid())
            throw new InvalidOperationException("An exact serial row without certificate reference metadata must fail closed to REVIEW.");

        var unreferencedFound = new CertificateLookupResultV1(
            "CERT_FOUND", 1, "", "", "EXACT_NORMALIZED_SERIAL");
        if (unreferencedFound.IsValid())
            throw new InvalidOperationException("CERT_FOUND must require a concrete certificate ID or path.");
    }
}
