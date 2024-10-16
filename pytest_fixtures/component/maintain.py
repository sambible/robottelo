# Satellite-maintain fixtures
import pytest
from broker import VMBroker

from robottelo import constants
from robottelo.config import settings
from robottelo.helpers import file_downloader
from robottelo.hosts import Satellite


@pytest.fixture(scope='module')
def sat_maintain(satellite_factory):
    if settings.remotedb.server:
        yield Satellite(settings.remotedb.server)
    else:
        sat = satellite_factory()
        yield sat
        VMBroker(hosts=[sat]).checkin()


@pytest.fixture(scope="function")
def setup_backup_tests(request, sat_maintain):
    """Teardown for backup/restore tests"""
    result = sat_maintain.execute('rm -rf /tmp/backup-*')
    assert result.status == 0

    def teardown_backup_tests():
        result = sat_maintain.execute('rm -rf /tmp/backup-*')
        assert result.status == 0

    request.addfinalizer(teardown_backup_tests)


@pytest.fixture(scope="module")
def module_synced_repos(sat_maintain):
    org = sat_maintain.api.Organization().create()
    manifests_path = file_downloader(
        file_url=settings.fake_manifest.url['default'], hostname=sat_maintain.hostname
    )[0]
    sat_maintain.cli.Subscription.upload({'file': manifests_path, 'organization-id': org.id})

    # sync custom repo
    cust_prod = sat_maintain.api.Product(organization=org).create()
    cust_repo = sat_maintain.api.Repository(
        url=settings.repos.yum_1.url, product=cust_prod
    ).create()
    cust_repo.sync()

    # sync RH repo
    product = sat_maintain.api.Product(name=constants.PRDS['rhae'], organization=org.id).search()[0]
    r_set = sat_maintain.api.RepositorySet(
        name=constants.REPOSET['rhae2'], product=product
    ).search()[0]
    payload = {'basearch': constants.DEFAULT_ARCHITECTURE, 'product_id': product.id}
    r_set.enable(data=payload)
    result = sat_maintain.api.Repository(name=constants.REPOS['rhae2']['name']).search(
        query={'organization_id': org.id}
    )
    rh_repo_id = result[0].id
    rh_repo = sat_maintain.api.Repository(id=rh_repo_id).read()
    rh_repo.sync()

    yield {'custom': cust_repo, 'rh': rh_repo}
