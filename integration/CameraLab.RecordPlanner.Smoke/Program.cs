using Dep.CameraLab.Contracts;

static void Require(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

var foundInference = new CameraLabInferenceV1(
    "scan-record-smoke-image", "", "", "SERIAL-1", 1.0, "FOUND", "ocr", "",
    "", "REVIEW", "", "", null, 0, "REVIEW", "");
var reviewInference = foundInference with { SerialStatus = "REVIEW" };

var noCert = new CertificateLookupResultV1("NO_CERT", 0, "", "", "");
var certFound = new CertificateLookupResultV1("CERT_FOUND", 1, "CERT-1", "PATH-1", "EXACT_NORMALIZED_SERIAL");
var reviewCert = new CertificateLookupResultV1("REVIEW", 2, "", "", "");
var notChecked = new CertificateLookupResultV1("NOT_CHECKED", 0, "", "", "");

var noCertRecord = CameraLabScanRecordPlannerV1.Create(" record-1 ", foundInference, noCert);
Require(noCertRecord.Accepted && noCertRecord.Record is not null && noCertRecord.Record.RecordId == "record-1",
    "Production-approved serial with NO_CERT must create a canonical persistent record");
Require(string.IsNullOrEmpty(noCertRecord.Record.PendingDestructionBin) && string.IsNullOrEmpty(noCertRecord.Record.DestructionStatus),
    "Record creation must never silently assign a destruction bin");

var foundRecord = CameraLabScanRecordPlannerV1.Create("record-2", foundInference, certFound);
Require(foundRecord.Accepted && foundRecord.Record is not null && foundRecord.Record.Certificate.LookupStatus == "CERT_FOUND",
    "Unique exact certificate result may be persisted for a production-approved serial");

Require(!CameraLabScanRecordPlannerV1.Create("record-3", reviewInference, noCert).Accepted,
    "NO_CERT must never become actionable when serial identity is not production-approved");
Require(!CameraLabScanRecordPlannerV1.Create("record-4", reviewInference, certFound).Accepted,
    "CERT_FOUND must never become actionable when serial identity is not production-approved");

var reviewRecord = CameraLabScanRecordPlannerV1.Create("record-5", reviewInference, reviewCert);
Require(reviewRecord.Accepted && reviewRecord.Record is not null && reviewRecord.Record.Certificate.LookupStatus == "REVIEW",
    "Ambiguous certificate state may be persisted only as non-actionable REVIEW");

var notCheckedRecord = CameraLabScanRecordPlannerV1.Create("record-6", reviewInference, notChecked);
Require(notCheckedRecord.Accepted && notCheckedRecord.Record is not null && notCheckedRecord.Record.Certificate.LookupStatus == "NOT_CHECKED",
    "Unavailable certificate data may be persisted only as non-actionable NOT_CHECKED");

Require(!CameraLabScanRecordPlannerV1.Create("", foundInference, noCert).Accepted,
    "Blank record identities must be rejected");
Require(!CameraLabScanRecordPlannerV1.Create("record-7", null, noCert).Accepted,
    "Missing inference must be rejected");
Require(!CameraLabScanRecordPlannerV1.Create("record-8", foundInference, null).Accepted,
    "Missing certificate result must be rejected");

var invalidFound = new CertificateLookupResultV1("CERT_FOUND", 2, "", "", "EXACT_NORMALIZED_SERIAL");
Require(!CameraLabScanRecordPlannerV1.Create("record-9", foundInference, invalidFound).Accepted,
    "Invalid or ambiguous CERT_FOUND structures must be rejected");

Console.WriteLine("Camera Lab scan record planner smoke checks passed.");
