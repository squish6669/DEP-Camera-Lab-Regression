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

Require(CameraLabContractV1.NormalizeSerial(" ab-12 34 ") == "AB1234", "Serial normalization must only remove separators and uppercase");

var eligibleLookup = new CertificateLookupRequestV1("SERIAL1", "FOUND", "contract-smoke-image");
Require(eligibleLookup.IsEligibleForLookup(), "Only a production-approved FOUND serial may enter certificate lookup");
Require(!new CertificateLookupRequestV1("SERIAL1", "REVIEW", "contract-smoke-image").IsEligibleForLookup(), "REVIEW serial must not enter certificate lookup");
Require(!new CertificateLookupRequestV1("", "FOUND", "contract-smoke-image").IsEligibleForLookup(), "Blank serial must not enter certificate lookup");

var notCheckedLookup = new ExactSerialCertificateLookupV1(null);
var notChecked = notCheckedLookup.Lookup(eligibleLookup);
Require(notChecked.LookupStatus == "NOT_CHECKED" && notChecked.IsValid(), "Missing external certificate index must remain NOT_CHECKED");

var noCertLookup = new ExactSerialCertificateLookupV1(Array.Empty<CertificateIndexRecordV1>());
var noCert = noCertLookup.Lookup(eligibleLookup);
Require(noCert.LookupStatus == "NO_CERT" && noCert.CertMatchCount == 0 && noCert.IsValid(), "Supplied index with no exact serial must return NO_CERT");

var exactLookup = new ExactSerialCertificateLookupV1(new[]
{
    new CertificateIndexRecordV1("SER-IAL1", "CERT-ID", "CERT-PATH")
});
var exact = exactLookup.Lookup(eligibleLookup);
Require(exact.LookupStatus == "CERT_FOUND" && exact.CertMatchCount == 1 && exact.CertId == "CERT-ID" && exact.IsValid(),
    "Unique exact normalized serial must be the only accepted certificate match");

var ambiguousLookup = new ExactSerialCertificateLookupV1(new[]
{
    new CertificateIndexRecordV1("SERIAL1", "CERT-A", "PATH-A"),
    new CertificateIndexRecordV1("SER-IAL1", "CERT-B", "PATH-B")
});
var ambiguous = ambiguousLookup.Lookup(eligibleLookup);
Require(ambiguous.LookupStatus == "REVIEW" && ambiguous.CertMatchCount == 2 && ambiguous.IsValid(),
    "Multiple exact normalized matches must remain REVIEW without selecting a certificate");
Require(string.IsNullOrEmpty(ambiguous.CertId) && string.IsNullOrEmpty(ambiguous.CertPath),
    "Ambiguous matches must not leak a guessed certificate selection");

var unsafeRequest = exactLookup.Lookup(new CertificateLookupRequestV1("SERIAL1", "REVIEW", "contract-smoke-image"));
Require(unsafeRequest.LookupStatus == "REVIEW" && unsafeRequest.CertMatchCount == 0,
    "Non-FOUND production serials must never enter certificate matching");

var invalidFound = new CertificateLookupResultV1("CERT_FOUND", 2, "", "", "EXACT_NORMALIZED_SERIAL");
Require(!invalidFound.IsValid(), "CERT_FOUND must never accept multiple matches");

var inference = new CameraLabInferenceV1(
    "contract-smoke-image", "", "no-vendor-evidence", "SERIAL1", 0, "FOUND", "contract-only", "",
    "", "REVIEW", "no-model-candidate", "", null, 0, "REVIEW", "");
var pending = new CameraLabScanRecordV1("record-contract-smoke", inference, noCert, "DS-01", "PENDING_DESTRUCTION");
Require(pending.IsValid(), "NO_CERT record may be assigned to an allowed DS bin");

var assignment = PendingDestructionPlannerV1.Evaluate(new PendingDestructionAssignmentRequestV1(inference, noCert, "ds-12"));
Require(assignment.Accepted && assignment.Assignment is not null && assignment.Assignment.Bin == "DS-12",
    "Production-approved NO_CERT record must be assignable only to canonical DS-01 through DS-12 bins");

var found = new CertificateLookupResultV1("CERT_FOUND", 1, "CERT-ID", "CERT-PATH", "EXACT_NORMALIZED_SERIAL");
var unsafePending = new CameraLabScanRecordV1("record-contract-smoke-2", inference, found, "DS-01", "PENDING_DESTRUCTION");
Require(!unsafePending.IsValid(), "CERT_FOUND record must never remain pending destruction");
Require(!PendingDestructionPlannerV1.Evaluate(new PendingDestructionAssignmentRequestV1(inference, found, "DS-01")).Accepted,
    "CERT_FOUND record must never receive a pending-destruction assignment");
Require(!PendingDestructionPlannerV1.Evaluate(new PendingDestructionAssignmentRequestV1(inference, ambiguous, "DS-01")).Accepted,
    "REVIEW certificate result must never receive a pending-destruction assignment");
Require(!PendingDestructionPlannerV1.Evaluate(new PendingDestructionAssignmentRequestV1(inference, notChecked, "DS-01")).Accepted,
    "NOT_CHECKED certificate result must never receive a pending-destruction assignment");
Require(!PendingDestructionPlannerV1.Evaluate(new PendingDestructionAssignmentRequestV1(inference, noCert, "DS-13")).Accepted,
    "Out-of-range DS bins must never be assigned");

var reviewInference = inference with { SerialStatus = "REVIEW" };
Require(!PendingDestructionPlannerV1.Evaluate(new PendingDestructionAssignmentRequestV1(reviewInference, noCert, "DS-01")).Accepted,
    "Non-FOUND serials must never enter pending destruction tracking");

var inference2 = inference with { Image = "contract-smoke-image-2", Serial = "SERIAL2" };
var pending2 = new CameraLabScanRecordV1("record-contract-smoke-2", inference2, noCert, "DS-01", "PENDING_DESTRUCTION");
var batch = PendingDestructionBatchPlannerV1.Build("batch-smoke", "ds-01", new[] { pending, pending2 });
Require(batch.Accepted && batch.Batch is not null && batch.Batch.IsValid() && batch.Batch.Bin == "DS-01" && batch.Batch.Entries.Count == 2,
    "A DS batch must accept only valid unique NO_CERT pending records from one canonical bin");

var crossBin = pending2 with { PendingDestructionBin = "DS-02" };
Require(!PendingDestructionBatchPlannerV1.Build("batch-cross-bin", "DS-01", new[] { pending, crossBin }).Accepted,
    "A destruction batch must never mix records from different DS bins");

var duplicateRecord = pending2 with { RecordId = pending.RecordId };
Require(!PendingDestructionBatchPlannerV1.Build("batch-duplicate-record", "DS-01", new[] { pending, duplicateRecord }).Accepted,
    "A destruction batch must reject duplicate persistent record identities");

var duplicateSerialInference = inference2 with { Serial = "SER-IAL1" };
var duplicateSerial = pending2 with { Inference = duplicateSerialInference };
Require(!PendingDestructionBatchPlannerV1.Build("batch-duplicate-serial", "DS-01", new[] { pending, duplicateSerial }).Accepted,
    "A destruction batch must reject duplicate normalized serial identities");

Require(!PendingDestructionBatchPlannerV1.Build("batch-cert-found", "DS-01", new[] { pending, unsafePending }).Accepted,
    "CERT_FOUND records must never enter a pending-destruction batch");
Require(!PendingDestructionBatchPlannerV1.Build("batch-invalid-bin", "DS-13", new[] { pending }).Accepted,
    "A destruction batch must remain confined to DS-01 through DS-12");
Require(!PendingDestructionBatchPlannerV1.Build("batch-empty", "DS-01", Array.Empty<CameraLabScanRecordV1>()).Accepted,
    "An empty destruction batch must not be created");

Console.WriteLine("Camera Lab app integration contract v1 smoke checks passed.");
