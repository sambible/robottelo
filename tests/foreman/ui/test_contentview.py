"""Test class for Content View UI

:Requirement: Contentview

:CaseAutomation: Automated

:CaseComponent: ContentViews

:team: Phoenix-content

:CaseImportance: High

"""

from fauxfactory import gen_string
import pytest
from widgetastic_patternfly4.dropdown import DropdownItemDisabled

from robottelo.constants import REPOS
from robottelo.exceptions import CLIReturnCodeError

from robottelo.constants import REPOS


@pytest.mark.tier2
def test_positive_create_cv(session, target_sat):
    """Able to create cv and search for it

    :id: 15666f4e-d6e6-448a-97df-fede20cc2d1a

    :steps:
        1. Create a CV in the UI
        2. Search for the CV

    :expectedresults: CV is visible in the UI, and matches the given name

    :CaseImportance: High
    """
    cv = gen_string('alpha')
    with target_sat.ui_session() as session:
        session.contentview_new.create(dict(name=cv))
        assert session.contentview_new.search(cv)[0]['Name'] == cv


@pytest.mark.tier2
def test_version_table_read(session, function_sca_manifest_org, target_sat):
    """Able to read CV version package details, which includes the Epoch tab

    :id: fe2a87c7-f148-40f2-b11a-c209a4807016

    :steps:
        1. Enable and Sync RHEL8 Base OS Repo
        2. Add repo to a CV
        3. Publish the CV
        4. Navigate to the published Version's page
        5. Filter packages to only an arbitrary package

    :expectedresults: The package is present, has the appropriate name, and has the epoch tab present

    :CaseImportance: Critical

    :BZ: 1911545

    :customerscenario: true
    """
    rh_repo_id = target_sat.api_factory.enable_sync_redhat_repo(
        REPOS['rhae2.9_el8'], function_sca_manifest_org.id
    )
    rh_repo = target_sat.api.Repository(id=rh_repo_id).read()
    packages = target_sat.api.Repository(id=rh_repo_id).packages()
    cv = target_sat.api.ContentView(organization=function_sca_manifest_org).create()
    cv = target_sat.api.ContentView(id=cv.id, repository=[rh_repo]).update(["repository"])
    cv.publish()
    with target_sat.ui_session() as session:
        session.organization.select(org_name=function_sca_manifest_org.name)
        response = session.contentview_new.read_version_table(
            cv.name, 'Version 1.0', 'rpmPackages', search_param=packages['results'][0]['nvra']
        )
        assert response[0]['Epoch'] == packages['results'][0]['epoch']
        assert response[0]['Name'] == packages['results'][0]['nvra']
        assert response[0]['Version'] == packages['results'][0]['version']
        assert response[0]['Release'] == packages['results'][0]['release']
        assert response[0]['Arch'] == packages['results'][0]['arch']


@pytest.mark.tier2
def test_no_blank_page_on_language_switch(session, target_sat, module_org):
    """Able to view the new CV UI when the language is set to something other
    than English

    :id: d8745aca-b199-4c7e-a970-b1f0f5c5d56c

    :steps:
        1. Change the Satellite system language to French
        2. Attempt to view the CV UI, and read the CV table

    :expectedresults: CV UI is visible, and isn't a blank page

    :BZ: 2163538

    :customerscenario: true
    """
    user_password = gen_string('alpha')
    user = target_sat.api.User(
        default_organization=module_org,
        organization=[module_org],
        password=user_password,
        admin=True,
    ).create()
    cv = target_sat.api.ContentView(organization=module_org).create()
    cv.publish()
    with target_sat.ui_session(user=user.login, password=user_password) as session:
        session.user.update(user.login, {'user.language': 'Français'})
        assert session.contentview_new.read_french_lang_cv()


def test_republish_metadata(session, function_sca_manifest_org, target_sat):
    """Verify that you can't republish metadata from the UI, and you can from the CLI
    :id: 96ef4fe5-dec4-4919-aa4d-b8806d90b654
    :steps:
        1. Enable and Sync RH Repo
        2. Add repo to a CV
        3. Publish the CV
        4. Navigate to the published Version's page
        5. Verify that you can't click the "republish metadata" option from the UI
        6. Verify that you can't republish metadata from the cli without the force option
        7. Verify that you can republish metadata from the CLI using the --force option
    :expectedresults: You can't republish RH Repo metadata from the UI, and can from the CLI with --force
    :CaseImportance: Critical
    :BZ: 2227271
    :customerscenario: true
    """
    rh_repo_id = target_sat.api_factory.enable_sync_redhat_repo(
        REPOS['rhae2.9_el8'], function_sca_manifest_org.id
    )
    rh_repo = target_sat.api.Repository(id=rh_repo_id).read()
    cv = target_sat.api.ContentView(organization=function_sca_manifest_org).create()
    cv = target_sat.api.ContentView(id=cv.id, repository=[rh_repo]).update(["repository"])
    cv.publish()
    version = cv.read().version[0].read()
    with target_sat.ui_session() as session:
        session.organization.select(org_name=function_sca_manifest_org.name)
        with pytest.raises(DropdownItemDisabled) as error:
            session.contentview_new.click_version_dropdown(
                cv.name, 'Version 1.0', "Republish repository metadata"
            )
        assert (
            'Item "Republish repository metadata" of dropdown ".//div[@data-ouia-component-id="cv-version-header-actions-dropdown"]" is disabled'
            in error.value.args[0]
        )
        with pytest.raises(CLIReturnCodeError) as error:
            target_sat.cli.ContentView.version_republish_repositories(
                {'id': version.id, 'force': 'false'}
            )
        assert (
            'Could not republish the Content View:\n  Metadata republishing is dangerous on content view versions with repositories with the \'Complete Mirroring\' mirroring policy.'
            in error.value.stderr
        )
        # This returns '' when successful, so this is just run to test that it doesn't throw any errors.
        target_sat.cli.ContentView.version_republish_repositories(
            {'id': version.id, 'force': 'true'}
        )
