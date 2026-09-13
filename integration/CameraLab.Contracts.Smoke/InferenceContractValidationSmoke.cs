using System.Runtime.CompilerServices;
using Dep.CameraLab.Contracts;

internal static class InferenceContractValidationSmoke
{
    [ModuleInitializer]
    internal static void Run()
    {
        static void Require(bool condition, string message)
        {
            if (!condition) throw new InvalidOperationException(message);
        }

        var valid = new CameraLabInferenceV1(
            "image-001.jpg",
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

        Require(CameraLabInferenceValidatorV1.Validate(valid).Accepted,
            "A complete OCR-evidence-backed production inference row must be operationally valid");

        Require(!CameraLabInferenceValidatorV1.Validate(valid with { Serial = "" }).Accepted,
            "FOUND serial status must never accept a blank serial");
        Require(!CameraLabInferenceValidatorV1.Validate(valid with { SerialEvidence = "" }).Accepted,
            "FOUND serial status must retain OCR evidence");
        Require(!CameraLabInferenceValidatorV1.Validate(valid with { ManufacturerEvidence = "" }).Accepted,
            "A populated manufacturer must retain OCR evidence");
        Require(!CameraLabInferenceValidatorV1.Validate(valid with { ModelEvidence = "" }).Accepted,
            "FOUND model status must retain OCR evidence");
        Require(!CameraLabInferenceValidatorV1.Validate(valid with { CapacityEvidence = "" }).Accepted,
            "READY or CONFIRM capacity must retain OCR evidence");
        Require(!CameraLabInferenceValidatorV1.Validate(valid with { Capacity = "", CapacityStatus = "READY" }).Accepted,
            "Missing capacity must fail closed unless its status is REVIEW");
        Require(!CameraLabInferenceValidatorV1.Validate(valid with { SerialStatus = "GUESSED" }).Accepted,
            "Unknown serial status must fail closed rather than becoming operational input");
        Require(!CameraLabInferenceValidatorV1.Validate(valid with { SerialScore = double.NaN }).Accepted,
            "Non-finite inference scores must fail closed");

        var unresolved = valid with
        {
            Manufacturer = "",
            ManufacturerEvidence = "",
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
        Require(CameraLabInferenceValidatorV1.Validate(unresolved).Accepted,
            "REVIEW must remain a valid unresolved state and must not force guessed values");
    }
}
