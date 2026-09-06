from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class HardeningContractsTest(unittest.TestCase):
    def test_android_uses_api_36_and_pinned_wrapper(self):
        app_gradle = (ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
        root_gradle = (ROOT / "android/build.gradle.kts").read_text(encoding="utf-8")
        wrapper = (ROOT / "android/gradle/wrapper/gradle-wrapper.properties").read_text(encoding="utf-8")

        self.assertIn('version "8.10.1"', root_gradle)
        self.assertIn("compileSdk = 36", app_gradle)
        self.assertIn("targetSdk = 36", app_gradle)
        self.assertIn("gradle-8.11.1-bin.zip", wrapper)
        self.assertRegex(wrapper, r"(?m)^distributionSha256Sum=[0-9a-f]{64}$")

    def test_ci_uses_locked_dependencies_wrapper_and_web_e2e(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        web_docker = (ROOT / "admin-web/Dockerfile").read_text(encoding="utf-8")
        backend_docker = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")

        self.assertIn("npm ci", workflow)
        self.assertIn("npm run test:e2e", workflow)
        self.assertIn("./android/gradlew -p android", workflow)
        self.assertIn("name: Итоговая проверка проекта", workflow)
        self.assertIn("COPY package.json package-lock.json", web_docker)
        self.assertIn("RUN npm ci", web_docker)
        self.assertNotIn("RUN npm install", web_docker)
        self.assertIn("COPY pyproject.toml requirements.lock", backend_docker)
        self.assertIn("pip install --no-cache-dir -r requirements.lock", backend_docker)
        self.assertIn("--no-build-isolation", backend_docker)

    def test_docker_contexts_exclude_local_secrets_and_generated_data(self):
        backend_ignore = (ROOT / "backend/.dockerignore").read_text(encoding="utf-8")
        web_ignore = (ROOT / "admin-web/.dockerignore").read_text(encoding="utf-8")

        for name, content in (("backend", backend_ignore), ("admin-web", web_ignore)):
            with self.subTest(context=name):
                self.assertIn(".env\n", content)
                self.assertIn(".env.*\n", content)
                self.assertIn("*.log\n", content)

        self.assertIn(".venv/\n", backend_ignore)
        self.assertIn(".pytest_cache/\n", backend_ignore)
        self.assertIn("tests/\n", backend_ignore)
        self.assertIn("node_modules/\n", web_ignore)
        self.assertIn("dist/\n", web_ignore)
        self.assertIn("playwright-report/\n", web_ignore)
        self.assertIn("test-results/\n", web_ignore)

    def test_production_uses_public_ip_https_with_shortlived_acme(self):
        compose = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
        caddy = (ROOT / "Caddyfile").read_text(encoding="utf-8")
        monitor = (ROOT / "scripts/production_monitor.py").read_text(encoding="utf-8")
        release = (ROOT / ".github/workflows/android-release.yml").read_text(encoding="utf-8")

        self.assertIn("caddy:2.11.3-alpine", compose)
        self.assertIn("CEH_PUBLIC_ORIGIN", compose)
        self.assertIn('"80:80"', compose)
        self.assertIn('"${CEH_PUBLIC_PORT:?Задайте CEH_PUBLIC_PORT}:443"', compose)
        self.assertNotIn("CEH_DOMAIN", compose)

        self.assertIn("http://{$CEH_PUBLIC_HOST}", caddy)
        self.assertIn("https://{$CEH_PUBLIC_HOST}", caddy)
        self.assertIn("profile shortlived", caddy)
        self.assertIn("disable_tlsalpn_challenge", caddy)
        self.assertIn("{$CEH_PUBLIC_WS_ORIGIN}", caddy)
        self.assertNotIn("CEH_DOMAIN", caddy)

        self.assertIn("CEH_PUBLIC_ORIGIN", monitor)
        self.assertNotIn("CEH_DOMAIN", monitor)
        self.assertIn("https://IP:PORT/", release)

    def test_production_bootstrap_can_be_disabled_after_initialization(self):
        compose = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
        first_run = (ROOT / "docs/FIRST_RUN.md").read_text(encoding="utf-8")
        production = (ROOT / "docs/PRODUCTION.md").read_text(encoding="utf-8")

        self.assertIn("BOOTSTRAP_ADMIN_LOGIN: '${BOOTSTRAP_ADMIN_LOGIN:-}'", compose)
        self.assertIn("BOOTSTRAP_ADMIN_PASSWORD: '${BOOTSTRAP_ADMIN_PASSWORD:-}'", compose)
        self.assertNotIn("BOOTSTRAP_ADMIN_LOGIN:?", compose)
        self.assertNotIn("BOOTSTRAP_ADMIN_PASSWORD:?", compose)
        self.assertIn("`BOOTSTRAP_ADMIN_LOGIN`", first_run)
        self.assertIn("`BOOTSTRAP_ADMIN_PASSWORD`", first_run)
        self.assertIn("удалены из production env, bootstrap отключён", first_run)
        self.assertIn("Bootstrap credentials являются временным секретом первого запуска", production)

    def test_all_android_workflows_build_through_wrapper(self):
        release = (ROOT / ".github/workflows/android-release.yml").read_text(encoding="utf-8")
        instrumented = (ROOT / ".github/workflows/android-instrumented.yml").read_text(encoding="utf-8")

        self.assertIn("./android/gradlew -p android", release)
        self.assertIn("./android/gradlew -p android", instrumented)
        self.assertNotIn('gradle-version: "8.9"', release)
        self.assertNotIn('gradle-version: "8.9"', instrumented)
        self.assertIn("api-level: 36", instrumented)

    def test_main_ruleset_requires_pr_and_both_ci_checks(self):
        ruleset = json.loads((ROOT / ".github/rulesets/main.json").read_text(encoding="utf-8"))
        types = {rule["type"] for rule in ruleset["rules"]}
        self.assertEqual(ruleset["enforcement"], "active")
        self.assertIn("pull_request", types)
        self.assertIn("non_fast_forward", types)
        self.assertIn("deletion", types)

        status_rule = next(rule for rule in ruleset["rules"] if rule["type"] == "required_status_checks")
        contexts = {item["context"] for item in status_rule["parameters"]["required_status_checks"]}
        self.assertEqual(
            contexts,
            {"Итоговая проверка проекта", "Проверить production и Android release-контракты"},
        )

    def test_lock_refresh_opens_pr_instead_of_pushing_main(self):
        workflow = (ROOT / ".github/workflows/dependency-snapshot.yml").read_text(encoding="utf-8")
        self.assertNotIn("git push origin HEAD:main", workflow)
        self.assertIn('BRANCH="automation/dependency-locks-${GITHUB_RUN_ID}"', workflow)
        self.assertIn("gh pr create", workflow)
        self.assertIn("pull-requests: write", workflow)

    def test_staging_acceptance_uses_verified_main_and_locked_dependencies(self):
        workflow = (ROOT / ".github/workflows/staging-acceptance.yml").read_text(encoding="utf-8")
        smoke = (ROOT / "scripts/staging_smoke.py").read_text(encoding="utf-8")

        required_fragments = (
            "permissions:\n  contents: read\n  actions: read",
            "refs/heads/main",
            "git/ref/heads/main",
            "Проверка проекта",
            "Проверка release-контрактов",
            "PROJECT_CI_COUNT",
            "RELEASE_CONTRACT_CI_COUNT",
            "pip install -r backend/requirements.lock",
            "pip install --no-deps -e './backend[dev]'",
            "Проверить точный backend release-контракт",
            "python scripts/verify_release_backend.py",
            "staging-backend-contract.json",
            "staging-release-preflight.json",
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, workflow)

        self.assertLess(
            workflow.index("Проверить точный backend release-контракт"),
            workflow.index("Выполнить read-only staging smoke"),
        )
        self.assertNotIn('--expected-schema-revision "20260904_09"', workflow)
        self.assertNotIn("run: pip install -e './backend[dev]'", workflow)

        self.assertIn('urlencode({"location_id": args.expected_location_id})', smoke)
        self.assertIn('additional_headers={"Authorization": f"Bearer {token}"}', smoke)
        self.assertNotIn('urlencode({"token": token', smoke)
        self.assertNotIn('"token": token, "location_id"', smoke)


if __name__ == "__main__":
    unittest.main()
