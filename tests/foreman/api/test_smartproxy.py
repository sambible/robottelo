"""Tests for the ``smart_proxies`` paths.

:Requirement: Smartproxy

:CaseAutomation: Automated

:CaseLevel: Component

:CaseComponent: Capsule

:Assignee: vsedmik

:TestType: Functional

:CaseImportance: Critical

:Upstream: No
"""
import pytest
from fauxfactory import gen_url
from nailgun import entities
from requests import HTTPError

from robottelo.api.utils import one_to_many_names
from robottelo.cleanup import capsule_cleanup
from robottelo.datafactory import parametrized
from robottelo.datafactory import valid_data_list
from robottelo.helpers import default_url_on_new_port
from robottelo.helpers import get_available_capsule_port


pytestmark = [pytest.mark.run_in_one_thread]


@pytest.fixture(scope='module')
def module_proxy_attrs(default_sat):
    """Find a ``SmartProxy``.

    Every Satellite has a built-in smart proxy, so searching for an
    existing smart proxy should always succeed.
    """
    smart_proxy = entities.SmartProxy().search(query={'search': f'url = {default_sat.url}:9090'})
    # Check that proxy is found and unpack it from the list
    assert len(smart_proxy) > 0, "No smart proxy is found"
    smart_proxy = smart_proxy[0]
    return set(smart_proxy.update_json([]).keys())


def _create_smart_proxy(request, **kwargs):
    """Create a Smart Proxy and add the finalizer"""
    proxy = entities.SmartProxy(**kwargs).create()

    @request.addfinalizer
    def _cleanup():
        capsule_cleanup(proxy.id)

    return proxy


@pytest.mark.skip_if_not_set('fake_capsules')
@pytest.mark.tier1
def test_negative_create_with_url():
    """Proxy creation with random URL

    :id: e48a6260-97e0-4234-a69c-77bbbcde85d6

    :expectedresults: Proxy is not created

    :CaseLevel: Component

    """
    # Create a random proxy
    with pytest.raises(HTTPError) as context:
        entities.SmartProxy(url=gen_url(scheme='https')).create()
    assert 'Unable to communicate' in context.value.response.text


@pytest.mark.skip_if_not_set('fake_capsules')
@pytest.mark.tier1
@pytest.mark.parametrize('name', **parametrized(valid_data_list()))
def test_positive_create_with_name(request, name):
    """Proxy creation with valid name

    :id: 0ffe0dc5-675e-45f4-b7e1-a14d3dd81f6e

    :expectedresults: Proxy is created

    :CaseLevel: Component

    :Parametrized: Yes

    """
    new_port = get_available_capsule_port()
    with default_url_on_new_port(9090, new_port) as url:
        proxy = _create_smart_proxy(request, name=name, url=url)
        assert proxy.name == name


@pytest.mark.skip_if_not_set('fake_capsules')
@pytest.mark.tier1
@pytest.mark.upgrade
def test_positive_delete():
    """Proxy deletion

    :id: 872bf12e-736d-43d1-87cf-2923966b59d0

    :expectedresults: Proxy is deleted

    :CaseLevel: Component

    :BZ: 1398695
    """
    new_port = get_available_capsule_port()
    with default_url_on_new_port(9090, new_port) as url:
        proxy = entities.SmartProxy(url=url).create()
        proxy.delete()
    with pytest.raises(HTTPError):
        proxy.read()


@pytest.mark.skip_if_not_set('fake_capsules')
@pytest.mark.tier1
def test_positive_update_name(request):
    """Proxy name update

    :id: f279640e-d7e9-48a3-aed8-7bf406e9d6f2

    :expectedresults: Proxy has the name updated

    :CaseLevel: Component

    """
    new_port = get_available_capsule_port()
    with default_url_on_new_port(9090, new_port) as url:
        proxy = _create_smart_proxy(request, url=url)
        for new_name in valid_data_list():
            proxy.name = new_name
            proxy = proxy.update(['name'])
            assert proxy.name == new_name


@pytest.mark.skip_if_not_set('fake_capsules')
@pytest.mark.tier1
def test_positive_update_url(request):
    """Proxy url update

    :id: 0305fd54-4e0c-4dd9-a537-d342c3dc867e

    :expectedresults: Proxy has the url updated

    :CaseLevel: Component

    """
    # Create fake capsule
    port = get_available_capsule_port()
    with default_url_on_new_port(9090, port) as url:
        proxy = _create_smart_proxy(request, url=url)
    # Open another tunnel to update url
    new_port = get_available_capsule_port()
    with default_url_on_new_port(9090, new_port) as url:
        proxy.url = url
        proxy = proxy.update(['url'])
        assert proxy.url == url


@pytest.mark.skip_if_not_set('fake_capsules')
@pytest.mark.tier1
def test_positive_update_organization(request):
    """Proxy name update with the home proxy

    :id: 62631275-7a92-4d34-a949-c56e0c4063f1

    :expectedresults: Proxy has the name updated

    :CaseLevel: Component

    """
    organizations = [entities.Organization().create() for _ in range(2)]
    newport = get_available_capsule_port()
    with default_url_on_new_port(9090, newport) as url:
        proxy = _create_smart_proxy(request, url=url)
        proxy.organization = organizations
        proxy = proxy.update(['organization'])
        assert {org.id for org in proxy.organization} == {org.id for org in organizations}


@pytest.mark.skip_if_not_set('fake_capsules')
@pytest.mark.tier1
def test_positive_update_location(request):
    """Proxy name update with the home proxy

    :id: e08eaaa9-7c11-4cda-bbe7-6d1f7c732569

    :expectedresults: Proxy has the name updated

    :CaseLevel: Component

    """
    locations = [entities.Location().create() for _ in range(2)]
    new_port = get_available_capsule_port()
    with default_url_on_new_port(9090, new_port) as url:
        proxy = _create_smart_proxy(request, url=url)
        proxy.location = locations
        proxy = proxy.update(['location'])
        assert {loc.id for loc in proxy.location} == {loc.id for loc in locations}


@pytest.mark.skip_if_not_set('fake_capsules')
@pytest.mark.tier2
@pytest.mark.upgrade
def test_positive_refresh_features(request):
    """Refresh smart proxy features, search for proxy by id

    :id: d0237546-702e-4d1a-9212-8391295174da

    :expectedresults: Proxy features are refreshed

    :CaseLevel: Integration

    """
    # Since we want to run multiple commands against our fake capsule, we
    # need the tunnel kept open in order not to allow different concurrent
    # test to claim it. Thus we want to manage the tunnel manually.

    # get an available port for our fake capsule
    new_port = get_available_capsule_port()
    with default_url_on_new_port(9090, new_port) as url:
        proxy = _create_smart_proxy(request, url=url)
        proxy.refresh()


@pytest.mark.skip_if_not_set('fake_capsules')
@pytest.mark.tier2
def test_positive_import_puppet_classes(request):
    """Import puppet classes from proxy

    :id: 385efd1b-6146-47bf-babf-0127ce5955ed

    :expectedresults: Puppet classes are imported from proxy

    :CaseLevel: Integration

    :BZ: 1398695
    """
    new_port = get_available_capsule_port()
    with default_url_on_new_port(9090, new_port) as url:
        proxy = _create_smart_proxy(request, url=url)
        result = proxy.import_puppetclasses()
        assert (
            "Successfully updated environment and puppetclasses from "
            "the on-disk puppet installation"
        ) in result['message']


"""Tests to see if the server returns the attributes it should.

Satellite should return a full description of an entity each time an entity
is created, read or updated. These tests verify that certain attributes
really are returned. The ``one_to_*_names`` functions know what names
Satellite may assign to fields.
"""


@pytest.mark.tier1
def test_positive_update_loc(module_proxy_attrs):
    """Update a smart proxy. Inspect the server's response.

    :id: 42d6b749-c047-4fd2-90ee-ffab7be558f9

    :expectedresults: The response contains some value for the ``location``
        field.

    :BZ: 1262037

    :CaseImportance: High

    :CaseLevel: Component

    """
    names = one_to_many_names('location')
    assert len(names & module_proxy_attrs) >= 1, f'None of {names} are in {module_proxy_attrs}'


@pytest.mark.tier1
def test_positive_update_org(module_proxy_attrs):
    """Update a smart proxy. Inspect the server's response.

    :id: fbde9f87-33db-4b95-a5f7-71a618460c84

    :expectedresults: The response contains some value for the
        ``organization`` field.

    :BZ: 1262037

    :CaseImportance: High

    :CaseLevel: Component

    """
    names = one_to_many_names('organization')
    assert len(names & module_proxy_attrs) >= 1, f'None of {names} are in {module_proxy_attrs}'
