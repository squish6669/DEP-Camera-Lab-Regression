using System.Runtime.CompilerServices;
using Dep.CameraLab.Contracts;

internal static class OperationalBridgeSmoke
{
    [ModuleInitializer]
    internal static void Run()
    {
        static void Require(bool condition, string message)
        {
            if (!condition) throw new InvalidOperationException(message);
        }

        var valid = new CameraLabInferenceV1(
            "image-bridge.jpg",
            "Western Digital",
            "ocr:western digital",
            "SERIAL123",
            1.0,
            "FOUND",
            "ocr:s/n SERIAL123",
            "SERIAL123",
            "MODEL-1",
            "FOUND",
            "ocr:model MODEL-1",
            "512 GB",
            512,
            1.0,
            "READY",
            "ocr:512GB");

        var certLookup = new ExactSerialCertificateLookupV1(new[]
        {
            new CertificateIndexRecordV1("SERIAL123", "CERT-1", "certs/CERT-1.pdf")
        });
        var found = CameraLabOperationalBridgeV1.Process("REC-1", valid, certLookup);
        Require(found.Accepted && found.Record?.Certificate.LookupStatus == "CERT_FOUND",
            "A validated FOUND serial with one exact cert must produce a CERT_FOUND scan record");

        var noCert = CameraLabOperationalBridgeV1.Process(
            "REC-2",
            valid,
            new ExactSerialCertificateLookupV1(Array.Empty<CertificateIndexRecordV1>()));
        Require(noCert.Accepted && noCert.Record?.Certificate.LookupStatus == "NO_CERT",
            "A validated FOUND serial with no exact cert must produce a NO_CERT scan record");

        var notChecked = CameraLabOperationalBridgeV1.Process("REC-3", valid, null);
        Require(notChecked.Accepted && notChecked.Record?.Certificate.LookupStatus == "NOT_CHECKED",
            "Unavailable external certificate data must remain NOT_CHECKED, never become a guessed NO_CERT");

        var unresolved = valid with
        {
            Serial = "",
            SerialStatus = "REVIEW",
            SerialEvidence = "",
            Model = "",
            ModelStatus = "REVIEW",
            ModelEvidence = "",
            Capacity = "",
            CapacityGB = null,
            CapacityStatus = "REVIEW",
            CapacityEvidence = ""
        };
        var review = CameraLabOperationalBridgeV1.Process("REC-4", unresolved, certLookup);
        Require(review.Accepted && review.Record?.Certificate.LookupStatus == "REVIEW",
            "Unresolved serial identity must remain REVIEW and must not enter cert matching");

        var invalid = valid with { SerialEvidence = "" };
        var rejected = CameraLabOperationalBridgeV1.Process("REC-5", invalid, certLookup);
        Require(!rejected.Accepted && rejected.Reason == "INVALID_INFERENCE",
            "Evidence-contract drift must fail before certificate lookup or persistence");
    }
}
