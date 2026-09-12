import unittest

from deploy.runtime_config import validate


class RuntimeConfigurationTests(unittest.TestCase):
    def configuration(self) -> dict[str, str]:
        return {"BEBSHAX_ENVIRONMENT": "production", "BEBSHAX_FRONTEND_BASE_URL": "https://app.example.test",
                "BEBSHAX_CORS_ORIGINS": "https://app.example.test", "BEBSHAX_CORS_ORIGIN_REGEX": "",
                "BEBSHAX_DEMO_MODE": "false", "BEBSHAX_ML_PERSONA_REQUIRED": "true",
                "BEBSHAX_ML_PERSONA_MANIFEST_SHA256": "0" * 64}

    def test_exact_public_origin_and_pinned_required_model_are_accepted(self) -> None:
        validate(self.configuration())

    def test_missing_model_pin_wildcard_cors_demo_and_development_are_rejected(self) -> None:
        for name, value in (("BEBSHAX_ENVIRONMENT", "development"), ("BEBSHAX_FRONTEND_BASE_URL", "http://localhost:5173"),
                            ("BEBSHAX_CORS_ORIGINS", "*"), ("BEBSHAX_CORS_ORIGIN_REGEX", ".*"),
                            ("BEBSHAX_ML_PERSONA_MANIFEST_SHA256", ""), ("BEBSHAX_ML_PERSONA_REQUIRED", "false"),
                            ("BEBSHAX_DEMO_MODE", "true")):
            with self.subTest(setting=name), self.assertRaises(ValueError):
                validate({**self.configuration(), name: value})


if __name__ == "__main__":
    unittest.main()