using Dep.CameraLab.Contracts;

static void Require(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

Require(CameraLabContractV1.AllowedDestructionBins.Count == 12, "DS allow-list must contain exactly 12 bins");
for (var i = 1; i <= 12; i++)
    Require(CameraLabContractV1.IsAllowedDestructionBin($"DS-{i:00}"), $"DS-{i:00} must be allowed");
Require(!CameraLabContractV1.IsAllowedDestructionBin("DS-00"), "DS-00 must be rejected");
Require(!CameraLabContractV1.IsAllowedDestructionBin("DS-13"), "DS-13 must be rejected");

var eligibleLookup = new CertificateLookupRequestV1("SERIAL1", "FOUND", "contract-smoke-image");
Require(eligibleLookup.IsEligibleForLookup(), "Only a production-approved FOUND serial may enter certificate lookup");
Require(!new CertificateLookupRequestV1("SERIAL1", "REVIEW", "contract-smoke-image").IsEligibleForLookup(), "REVIEW serial must not enter certificate lookup");
Require(!new CertificateLookupRequestV1("", "FOUND", "contract-smoke-image").IsEligibleForLookup(), "Blank serial must not enter certificate lookup");

var notChecked = new CertificateLookupResultV1("NOT_CHECKED", 0, "", "", "");
Require(notChecked.IsValid(), "NOT_CHECKED without external cert data must be valid");

var ambiguous = new CertificateLookupResultV1("REVIEW", 2, "", "", "");
Require(ambiguous.IsValid(), "Ambiguous exact matches must remain REVIEW without selecting a certificate");

var invalidFound = new CertificateLookupResultV1("CERT_FOUND", 2, "", "", "EXACT_NORMALIZED_SERIAL");
Require(!invalidFound.IsValid(), "CERT_FOUND must never accept multiple matches");

var noCert = new CertificateLookupResultV1("NO_CERT", 0, "", "", "");
var inference = new CameraLabInferenceV1(
    "contract-smoke-image", "", "no-vendor-evidence", "SERIAL1", 0, "FOUND", "contract-only", "",
    "", "REVIEW", "no-model-candidate", "", null, 0, "REVIEW", "");
var pending = new CameraLabScanRecordV1("record-contract-smoke", inference, noCert, "DS-01", "PENDING_DESTRUCTION");
Require(pending.IsValid(), "NO_CERT record may be assigned to an allowed DS bin");

var found = new CertificateLookupResultV1("CERT_FOUND", 1, "CERT-ID", "CERT-PATH", "EXACT_NORMALIZED_SERIAL");
var unsafePending = new CameraLabScanRecordV1("record-contract-smoke-2", inference, found, "DS-01", "PENDING_DESTRUCTION");
Require(!unsafePending.IsValid(), "CERT_FOUND record must never remain pending destruction");

Console.WriteLine("Camera Lab app integration contract v1 smoke checks passed.");
