import unittest

from scripts.ops.env_template import render_template


class EnvironmentTemplateTests(unittest.TestCase):
    def test_template_discards_every_value_and_retired_provider_name(self) -> None:
        result = render_template("BEBSHAX_JWT_SECRET=synthetic-sentinel\nOPENROUTER_API_KEY=synthetic-sentinel\nOLLAMA_API_BASE=retired\n",
                                 "class Settings:\n    jwt_secret: str = ''\n    ml_persona_required: bool = False\n")
        self.assertNotIn("synthetic-sentinel", result)
        self.assertNotIn("OLLAMA", result)
        self.assertIn("BEBSHAX_ML_PERSONA_REQUIRED=\n", result)
        self.assertIn("OPENROUTER_API_KEY=\n", result)
        for line in result.splitlines():
            if not line.startswith("#"):
                self.assertEqual(line.split("=", 1)[1], "")

    def test_template_is_idempotent_and_preserves_documented_adapter_settings(self) -> None:
        source = "class Settings:\n    cors_origins: str = ''\n"
        result = render_template("BEBSHAX_ADAPTER_OPTION=\n", source)
        self.assertIn("BEBSHAX_ADAPTER_OPTION=\n", result)
        self.assertIn("BEBSHAX_OPENROUTER_MODELS=\n", result)
        self.assertEqual(render_template(result, source), result)


if __name__ == "__main__":
    unittest.main()