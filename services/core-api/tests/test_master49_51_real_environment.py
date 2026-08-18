from app.acceptance.real_environment import (
    CorporateIdentityAcceptance,
    PhysicalDeviceAcceptance,
    RealDataAcceptance,
    corporate_identity_accepted,
    physical_device_accepted,
    real_data_accepted,
)


def test_ci_identity_fixture_cannot_become_corporate_acceptance() -> None:
    synthetic_like = CorporateIdentityAcceptance(
        environment_class="MANAGED_STAGING",
        issuer="https://issuer",
        tenant="tenant",
        employee_id_claim="employee_id",
        warehouse_scope_claim="warehouse_scope",
        stale_token_rejected=True,
        exit_revocation_passed=True,
        workload_identity_passed=True,
        service_account_passed=True,
        provenance="ci:oidc",
        approver="security",
    )
    assert not corporate_identity_accepted(synthetic_like)

    real = CorporateIdentityAcceptance(
        environment_class="CORPORATE_REAL",
        issuer="https://corp-idp",
        tenant="corp-tenant",
        employee_id_claim="employee_id",
        warehouse_scope_claim="warehouse_scope",
        stale_token_rejected=True,
        exit_revocation_passed=True,
        workload_identity_passed=True,
        service_account_passed=True,
        provenance="oidc-acceptance:42",
        approver="security-owner",
    )
    assert corporate_identity_accepted(real)


def test_device_acceptance_requires_physical_attested_device_and_lifecycle() -> None:
    build_only = PhysicalDeviceAcceptance(
        environment_class="REAL_BUILD",
        platform="android",
        device_model="Zebra TC5x",
        mdm_identity="mdm:1",
        integrity_provider="play-integrity",
        integrity_passed=True,
        lost_replace_passed=True,
        offline_reconnect_passed=True,
        provenance="build:1",
        approver="device-owner",
    )
    assert not physical_device_accepted(build_only)

    physical = PhysicalDeviceAcceptance(
        environment_class="PHYSICAL_DEVICE",
        platform="android",
        device_model="Zebra TC5x",
        mdm_identity="mdm:1",
        integrity_provider="play-integrity",
        integrity_passed=True,
        lost_replace_passed=True,
        offline_reconnect_passed=True,
        provenance="device-run:1",
        approver="device-owner",
    )
    assert physical_device_accepted(physical)


def test_real_data_requires_exact_reconciliation_and_sha256() -> None:
    good = RealDataAcceptance(
        environment_class="MANAGED_STAGING",
        dataset_key="hr_roster",
        source_hash="a" * 64,
        source_rows=1000,
        reconciled_rows=1000,
        mismatch_rows=0,
        provenance="reconcile:1",
        approver="data-owner",
    )
    assert real_data_accepted(good)

    mismatch = RealDataAcceptance(
        environment_class="MANAGED_STAGING",
        dataset_key="hr_roster",
        source_hash="a" * 64,
        source_rows=1000,
        reconciled_rows=999,
        mismatch_rows=1,
        provenance="reconcile:2",
        approver="data-owner",
    )
    assert not real_data_accepted(mismatch)

    invalid_hash = RealDataAcceptance(
        environment_class="MANAGED_STAGING",
        dataset_key="hr_roster",
        source_hash="z" * 64,
        source_rows=1000,
        reconciled_rows=1000,
        mismatch_rows=0,
        provenance="reconcile:3",
        approver="data-owner",
    )
    assert not real_data_accepted(invalid_hash)
