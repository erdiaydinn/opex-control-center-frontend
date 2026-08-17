from app.acceptance.real_environment import CorporateIdentityAcceptance, PhysicalDeviceAcceptance, RealDataAcceptance, corporate_identity_accepted, physical_device_accepted, real_data_accepted


def test_ci_identity_fixture_cannot_become_corporate_acceptance():
    e=CorporateIdentityAcceptance('MANAGED_STAGING','https://issuer','tenant','employee_id','warehouse_scope',True,True,True,True,'ci:oidc','security')
    assert not corporate_identity_accepted(e)
    assert corporate_identity_accepted(CorporateIdentityAcceptance('CORPORATE_REAL','https://corp-idp','corp-tenant','employee_id','warehouse_scope',True,True,True,True,'oidc-acceptance:42','security-owner'))


def test_device_acceptance_requires_physical_attested_device_and_lifecycle():
    assert not physical_device_accepted(PhysicalDeviceAcceptance('REAL_BUILD','android','Zebra TC5x','mdm:1','play-integrity',True,True,True,'build:1','device-owner'))
    assert physical_device_accepted(PhysicalDeviceAcceptance('PHYSICAL_DEVICE','android','Zebra TC5x','mdm:1','play-integrity',True,True,True,'device-run:1','device-owner'))


def test_real_data_requires_exact_reconciliation_and_source_hash():
    good=RealDataAcceptance('MANAGED_STAGING','hr_roster','a'*64,1000,1000,0,'reconcile:1','data-owner')
    assert real_data_accepted(good)
    assert not real_data_accepted(RealDataAcceptance('MANAGED_STAGING','hr_roster','a'*64,1000,999,1,'reconcile:2','data-owner'))
