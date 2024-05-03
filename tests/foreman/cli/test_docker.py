"""Tests for the Docker feature.

:Requirement: Docker

:CaseAutomation: Automated

:CaseImportance: High

"""
from random import choice, randint

from fauxfactory import gen_string, gen_url
import pytest

from robottelo.config import settings
from robottelo.constants import (
    CONTAINER_REGISTRY_HUB,
    CONTAINER_RH_REGISTRY_UPSTREAM_NAME,
    CONTAINER_UPSTREAM_NAME,
    REPO_TYPE,
)
from robottelo.exceptions import CLIReturnCodeError
from robottelo.utils.datafactory import (
    invalid_docker_upstream_names,
    parametrized,
    valid_docker_repository_names,
    valid_docker_upstream_names,
)


def _repo(sat, product_id, name=None, upstream_name=None, url=None):
    """Creates a Docker-based repository.

    :param product_id: ID of the ``Product``.
    :param str name: Name for the repository. If ``None`` then a random
        value will be generated.
    :param str upstream_name: A valid name of an existing upstream repository.
        If ``None`` then defaults to CONTAINER_UPSTREAM_NAME constant.
    :param str url: URL of repository. If ``None`` then defaults to
        CONTAINER_REGISTRY_HUB constant.
    :return: A ``Repository`` object.
    """
    return sat.cli_factory.make_repository(
        {
            'content-type': REPO_TYPE['docker'],
            'docker-upstream-name': upstream_name or CONTAINER_UPSTREAM_NAME,
            'name': name or gen_string('alpha', 5),
            'product-id': product_id,
            'url': url or CONTAINER_REGISTRY_HUB,
        }
    )


def _content_view(sat, repo_id, org_id):
    """Create a content view and link it to the given repository."""
    content_view = sat.cli_factory.make_content_view(
        {'composite': False, 'organization-id': org_id}
    )
    sat.cli.ContentView.add_repository({'id': content_view['id'], 'repository-id': repo_id})
    return sat.cli.ContentView.info({'id': content_view['id']})


@pytest.fixture
def repo(module_product, target_sat):
    return _repo(target_sat, module_product.id)


@pytest.fixture
def content_view(module_org, target_sat, repo):
    return _content_view(target_sat, repo['id'], module_org.id)


@pytest.fixture
def content_view_publish(content_view, target_sat):
    target_sat.cli.ContentView.publish({'id': content_view['id']})
    content_view = target_sat.cli.ContentView.info({'id': content_view['id']})
    return target_sat.cli.ContentView.version_info({'id': content_view['versions'][0]['id']})


@pytest.fixture
def content_view_promote(content_view_publish, module_lce, target_sat):
    target_sat.cli.ContentView.version_promote(
        {
            'id': content_view_publish['id'],
            'to-lifecycle-environment-id': module_lce.id,
        }
    )
    return target_sat.cli.ContentView.version_info({'id': content_view_publish['id']})


class TestDockerManifest:
    """Tests related to docker manifest command

    :CaseComponent: Repositories

    :team: Phoenix-content
    """

    @pytest.mark.tier2
    def test_positive_read_docker_tags(self, repo, module_target_sat):
        """docker manifest displays tags information for a docker manifest

        :id: 59b605b5-ac2d-46e3-a85e-a259e78a07a8

        :expectedresults: docker manifest displays tags info for a docker
            manifest

        :CaseImportance: Medium

        :BZ: 1658274
        """
        module_target_sat.cli.Repository.synchronize({'id': repo['id']})
        # Grab all available manifests related to repository
        manifests_list = module_target_sat.cli.Docker.manifest.list({'repository-id': repo['id']})
        # Some manifests do not have tags associated with it, ignore those
        # because we want to check the tag information
        manifests = [m_iter for m_iter in manifests_list if m_iter['tags'] != '']
        assert manifests
        tags_list = module_target_sat.cli.Docker.tag.list({'repository-id': repo['id']})
        # Extract tag names for the repository out of docker tag list
        repo_tag_names = [tag['tag'] for tag in tags_list]
        for manifest in manifests:
            manifest_info = module_target_sat.cli.Docker.manifest.info({'id': manifest['id']})
            # Check that manifest's tag is listed in tags for the repository
            for t_iter in manifest_info['tags']:
                assert t_iter['name'] in repo_tag_names


class TestDockerRepository:
    """Tests specific to performing CRUD methods against ``Docker`` repositories.

    :CaseComponent: Repositories

    :team: Phoenix-content
    """

    @pytest.mark.tier1
    @pytest.mark.parametrize('name', **parametrized(valid_docker_repository_names()))
    def test_positive_create_with_name(self, module_product, name, module_target_sat):
        """Create one Docker-type repository

        :id: e82a36c8-3265-4c10-bafe-c7e07db3be78

        :parametrized: yes

        :expectedresults: A repository is created with a Docker upstream
         repository.

        :CaseImportance: Critical
        """
        repo = _repo(module_target_sat, module_product.id, name)
        assert repo['name'] == name
        assert repo['upstream-repository-name'] == CONTAINER_UPSTREAM_NAME
        assert repo['content-type'] == REPO_TYPE['docker']

    @pytest.mark.tier2
    def test_positive_create_repos_using_same_product(
        self, module_org, module_product, module_target_sat
    ):
        """Create multiple Docker-type repositories

        :id: 6dd25cf4-f8b6-4958-976a-c116daf27b44

        :expectedresults: Multiple docker repositories are created with a
            Docker upstream repository and they all belong to the same product.

        """
        repo_names = set()
        for _ in range(randint(2, 5)):
            repo = _repo(module_target_sat, module_product.id)
            repo_names.add(repo['name'])
        product = module_target_sat.cli.Product.info(
            {'id': module_product.id, 'organization-id': module_org.id}
        )
        assert repo_names.issubset({repo_['repo-name'] for repo_ in product['content']})

    @pytest.mark.tier2
    def test_positive_create_repos_using_multiple_products(self, module_org, module_target_sat):
        """Create multiple Docker-type repositories on multiple
        products.

        :id: 43f4ab0d-731e-444e-9014-d663ff945f36

        :expectedresults: Multiple docker repositories are created with a
            Docker upstream repository and they all belong to their respective
            products.

        """
        for _ in range(randint(2, 5)):
            product = module_target_sat.cli_factory.make_product_wait(
                {'organization-id': module_org.id}
            )
            repo_names = set()
            for _ in range(randint(2, 3)):
                repo = _repo(module_target_sat, product['id'])
                repo_names.add(repo['name'])
            product = module_target_sat.cli.Product.info(
                {'id': product['id'], 'organization-id': module_org.id}
            )
            assert repo_names == {repo_['repo-name'] for repo_ in product['content']}

    @pytest.mark.tier1
    def test_positive_sync(self, repo, module_target_sat):
        """Create and sync a Docker-type repository

        :id: bff1d40e-181b-48b2-8141-8c86e0db62a2

        :expectedresults: A repository is created with a Docker repository and
            it is synchronized.

        :CaseImportance: Critical
        """
        assert int(repo['content-counts']['container-image-manifests']) == 0
        module_target_sat.cli.Repository.synchronize({'id': repo['id']})
        repo = module_target_sat.cli.Repository.info({'id': repo['id']})
        assert int(repo['content-counts']['container-image-manifests']) > 0

    @pytest.mark.tier1
    @pytest.mark.parametrize('new_name', **parametrized(valid_docker_repository_names()))
    def test_positive_update_name(self, repo, new_name, module_target_sat):
        """Create a Docker-type repository and update its name.

        :id: 8b3a8496-e9bd-44f1-916f-6763a76b9b1b

        :parametrized: yes

        :expectedresults: A repository is created with a Docker upstream
            repository and that its name can be updated.

        :CaseImportance: Critical
        """
        module_target_sat.cli.Repository.update(
            {'id': repo['id'], 'new-name': new_name, 'url': repo['url']}
        )
        repo = module_target_sat.cli.Repository.info({'id': repo['id']})
        assert repo['name'] == new_name

    @pytest.mark.tier1
    @pytest.mark.parametrize('new_upstream_name', **parametrized(valid_docker_upstream_names()))
    def test_positive_update_upstream_name(self, repo, new_upstream_name, module_target_sat):
        """Create a Docker-type repository and update its upstream name.

        :id: 1a6985ed-43ec-4ea6-ba27-e3870457ac56

        :parametrized: yes

        :expectedresults: A repository is created with a Docker upstream
            repository and that its upstream name can be updated.

        :CaseImportance: Critical
        """
        module_target_sat.cli.Repository.update(
            {
                'docker-upstream-name': new_upstream_name,
                'id': repo['id'],
                'url': repo['url'],
            }
        )
        repo = module_target_sat.cli.Repository.info({'id': repo['id']})
        assert repo['upstream-repository-name'] == new_upstream_name

    @pytest.mark.tier1
    @pytest.mark.parametrize('new_upstream_name', **parametrized(invalid_docker_upstream_names()))
    def test_negative_update_upstream_name(self, repo, new_upstream_name, module_target_sat):
        """Attempt to update upstream name for a Docker-type repository.

        :id: 798651af-28b2-4907-b3a7-7c560bf66c7c

        :parametrized: yes

        :expectedresults: A repository is created with a Docker upstream
            repository and that its upstream name can not be updated with
            invalid values.

        :CaseImportance: Critical
        """
        with pytest.raises(CLIReturnCodeError, match='Validation failed: Docker upstream name'):
            module_target_sat.cli.Repository.update(
                {
                    'docker-upstream-name': new_upstream_name,
                    'id': repo['id'],
                    'url': repo['url'],
                }
            )

    @pytest.mark.skip_if_not_set('docker')
    @pytest.mark.tier1
    def test_positive_create_with_long_upstream_name(self, module_product, module_target_sat):
        """Create a docker repository with upstream name longer than 30
        characters

        :id: 4fe47c02-a8bd-4630-9102-189a9d268b83

        :customerscenario: true

        :BZ: 1424689

        :expectedresults: docker repository is successfully created

        :CaseImportance: Critical
        """
        repo = _repo(
            module_target_sat,
            module_product.id,
            upstream_name=CONTAINER_RH_REGISTRY_UPSTREAM_NAME,
            url=settings.docker.external_registry_1,
        )
        assert repo['upstream-repository-name'] == CONTAINER_RH_REGISTRY_UPSTREAM_NAME

    @pytest.mark.skip_if_not_set('docker')
    @pytest.mark.tier1
    def test_positive_update_with_long_upstream_name(self, repo, module_target_sat):
        """Create a docker repository and update its upstream name with longer
        than 30 characters value

        :id: 97260cce-9677-4a3e-942b-e95e2714500a

        :BZ: 1424689

        :expectedresults: docker repository is successfully updated

        :CaseImportance: Critical
        """
        module_target_sat.cli.Repository.update(
            {
                'docker-upstream-name': CONTAINER_RH_REGISTRY_UPSTREAM_NAME,
                'id': repo['id'],
                'url': settings.docker.external_registry_1,
            }
        )
        repo = module_target_sat.cli.Repository.info({'id': repo['id']})
        assert repo['upstream-repository-name'] == CONTAINER_RH_REGISTRY_UPSTREAM_NAME

    @pytest.mark.tier2
    def test_positive_update_url(self, repo, module_target_sat):
        """Create a Docker-type repository and update its URL.

        :id: 73caacd4-7f17-42a7-8d93-3dee8b9341fa

        :expectedresults: A repository is created with a Docker upstream
            repository and that its URL can be updated.
        """
        new_url = gen_url()
        module_target_sat.cli.Repository.update({'id': repo['id'], 'url': new_url})
        repo = module_target_sat.cli.Repository.info({'id': repo['id']})
        assert repo['url'] == new_url

    @pytest.mark.tier1
    def test_positive_delete_by_id(self, repo, module_target_sat):
        """Create and delete a Docker-type repository

        :id: ab1e8228-92a8-45dc-a863-7181711f2745

        :expectedresults: A repository with a upstream repository is created
            and then deleted.

        :CaseImportance: Critical
        """
        module_target_sat.cli.Repository.delete({'id': repo['id']})
        with pytest.raises(CLIReturnCodeError):
            module_target_sat.cli.Repository.info({'id': repo['id']})

    @pytest.mark.tier2
    def test_positive_delete_random_repo_by_id(self, module_org, module_target_sat):
        """Create Docker-type repositories on multiple products and
        delete a random repository from a random product.

        :id: d4db5eaa-7379-4788-9b72-76f2589d8f20

        :expectedresults: Random repository can be deleted from random product
            without altering the other products.
        """
        products = [
            module_target_sat.cli_factory.make_product_wait({'organization-id': module_org.id})
            for _ in range(randint(2, 5))
        ]
        repos = []
        for product in products:
            for _ in range(randint(2, 3)):
                repos.append(_repo(module_target_sat, product['id']))
        # Select random repository and delete it
        repo = choice(repos)
        repos.remove(repo)
        module_target_sat.cli.Repository.delete({'id': repo['id']})
        with pytest.raises(CLIReturnCodeError):
            module_target_sat.cli.Repository.info({'id': repo['id']})
        # Verify other repositories were not touched
        product_ids = [product['id'] for product in products]
        for repo in repos:
            result = module_target_sat.cli.Repository.info({'id': repo['id']})
            assert result['product']['id'] in product_ids


class TestDockerContentView:
    """Tests specific to using ``Docker`` repositories with Content Views.

    :CaseComponent: ContentViews

    :team: Phoenix-content
    """

    @pytest.mark.tier2
    def test_positive_add_docker_repo_by_id(self, module_org, repo, module_target_sat):
        """Add one Docker-type repository to a non-composite content view

        :id: 87d6c7bb-92f8-4a32-8ad2-2a1af896500b

        :expectedresults: A repository is created with a Docker repository and
            the product is added to a non-composite content view
        """
        content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': False, 'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.add_repository(
            {'id': content_view['id'], 'repository-id': repo['id']}
        )
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        assert repo['id'] in [repo_['id'] for repo_ in content_view['container-image-repositories']]

    @pytest.mark.tier2
    def test_positive_add_docker_repos_by_id(self, module_org, module_product, module_target_sat):
        """Add multiple Docker-type repositories to a non-composite CV.

        :id: 2eb19e28-a633-4c21-9469-75a686c83b34

        :expectedresults: Repositories are created with Docker upstream
            repositories and the product is added to a non-composite content
            view.
        """
        repos = [_repo(module_target_sat, module_product.id) for _ in range(randint(2, 5))]
        content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': False, 'organization-id': module_org.id}
        )
        for repo in repos:
            module_target_sat.cli.ContentView.add_repository(
                {'id': content_view['id'], 'repository-id': repo['id']}
            )
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})

        assert {repo['id'] for repo in repos} == {
            repo['id'] for repo in content_view['container-image-repositories']
        }

    @pytest.mark.tier2
    def test_positive_add_synced_docker_repo_by_id(self, module_org, repo, module_target_sat):
        """Create and sync a Docker-type repository

        :id: 6f51d268-ed23-48ab-9dea-cd3571daa647

        :expectedresults: A repository is created with a Docker repository and
            it is synchronized.
        """
        module_target_sat.cli.Repository.synchronize({'id': repo['id']})
        repo = module_target_sat.cli.Repository.info({'id': repo['id']})
        assert int(repo['content-counts']['container-image-manifests']) > 0

        content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': False, 'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.add_repository(
            {'id': content_view['id'], 'repository-id': repo['id']}
        )
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        assert repo['id'] in [repo_['id'] for repo_ in content_view['container-image-repositories']]

    @pytest.mark.tier2
    def test_positive_add_docker_repo_by_id_to_ccv(
        self, module_org, content_view, module_target_sat
    ):
        """Add one Docker-type repository to a composite content view

        :id: 8e2ef5ba-3cdf-4ef9-a22a-f1701e20a5d5

        :expectedresults: A repository is created with a Docker repository and
            the product is added to a content view which is then added to a
            composite content view.

        :BZ: 1359665
        """
        module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        assert len(content_view['versions']) == 1
        comp_content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': True, 'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.update(
            {
                'id': comp_content_view['id'],
                'component-ids': content_view['versions'][0]['id'],
            }
        )
        comp_content_view = module_target_sat.cli.ContentView.info({'id': comp_content_view['id']})
        assert content_view['versions'][0]['id'] in [
            component['id'] for component in comp_content_view['components']
        ]

    @pytest.mark.tier2
    def test_positive_add_docker_repos_by_id_to_ccv(
        self, module_org, module_product, module_target_sat
    ):
        """Add multiple Docker-type repositories to a composite content view.

        :id: b79cbc97-3dba-4059-907d-19316684d569

        :expectedresults: One repository is created with a Docker upstream
            repository and the product is added to a random number of content
            views which are then added to a composite content view.

        :BZ: 1359665
        """
        cv_versions = []
        for _ in range(randint(2, 5)):
            content_view = module_target_sat.cli_factory.make_content_view(
                {'composite': False, 'organization-id': module_org.id}
            )
            repo = _repo(module_target_sat, module_product.id)
            module_target_sat.cli.ContentView.add_repository(
                {'id': content_view['id'], 'repository-id': repo['id']}
            )
            module_target_sat.cli.ContentView.publish({'id': content_view['id']})
            content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
            assert len(content_view['versions']) == 1
            cv_versions.append(content_view['versions'][0])
        comp_content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': True, 'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.update(
            {
                'component-ids': [cv_version['id'] for cv_version in cv_versions],
                'id': comp_content_view['id'],
            }
        )
        comp_content_view = module_target_sat.cli.ContentView.info({'id': comp_content_view['id']})
        comp_ids = [component['id'] for component in comp_content_view['components']]
        for cv_version in cv_versions:
            assert cv_version['id'] in comp_ids

    @pytest.mark.tier2
    def test_positive_publish_with_docker_repo(self, content_view, module_target_sat):
        """Add Docker-type repository to content view and publish it once.

        :id: 28480de3-ffb5-4b8e-8174-fffffeef6af4

        :expectedresults: One repository is created with a Docker upstream
            repository and the product is added to a content view which is then
            published only once.
        """
        assert len(content_view['versions']) == 0
        module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        assert len(content_view['versions']) == 1

    @pytest.mark.tier2
    def test_positive_publish_with_docker_repo_composite(
        self, content_view, module_org, module_target_sat
    ):
        """Add Docker-type repository to composite CV and publish it once.

        :id: 2d75419b-73ed-4f29-ae0d-9af8d9624c87

        :expectedresults: One repository is created with a Docker upstream
            repository and the product is added to a content view which is then
            published once and added to a composite content view which is also
            published once.

        :BZ: 1359665
        """
        assert len(content_view['versions']) == 0

        module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        assert len(content_view['versions']) == 1

        comp_content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': True, 'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.update(
            {
                'component-ids': content_view['versions'][0]['id'],
                'id': comp_content_view['id'],
            }
        )
        comp_content_view = module_target_sat.cli.ContentView.info({'id': comp_content_view['id']})
        assert content_view['versions'][0]['id'] in [
            component['id'] for component in comp_content_view['components']
        ]

        module_target_sat.cli.ContentView.publish({'id': comp_content_view['id']})
        comp_content_view = module_target_sat.cli.ContentView.info({'id': comp_content_view['id']})
        assert len(comp_content_view['versions']) == 1

    @pytest.mark.tier2
    def test_positive_publish_multiple_with_docker_repo(self, content_view, module_target_sat):
        """Add Docker-type repository to content view and publish it multiple
        times.

        :id: 33c1b2ee-ae8a-4a7e-8254-123d97aaaa58

        :expectedresults: One repository is created with a Docker upstream
            repository and the product is added to a content view which is then
            published multiple times.
        """
        assert len(content_view['versions']) == 0

        publish_amount = randint(2, 5)
        for _ in range(publish_amount):
            module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        assert len(content_view['versions']) == publish_amount

    @pytest.mark.tier2
    def test_positive_publish_multiple_with_docker_repo_composite(
        self, module_org, content_view, module_target_sat
    ):
        """Add Docker-type repository to content view and publish it multiple
        times.

        :id: 014adf90-d399-4a99-badb-76ee03a2c350

        :expectedresults: One repository is created with a Docker upstream
            repository and the product is added to a content view which is then
            added to a composite content view which is then published multiple
            times.

        :BZ: 1359665
        """
        assert len(content_view['versions']) == 0

        module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        assert len(content_view['versions']) == 1

        comp_content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': True, 'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.update(
            {
                'component-ids': content_view['versions'][0]['id'],
                'id': comp_content_view['id'],
            }
        )
        comp_content_view = module_target_sat.cli.ContentView.info({'id': comp_content_view['id']})
        assert content_view['versions'][0]['id'] in [
            component['id'] for component in comp_content_view['components']
        ]

        publish_amount = randint(2, 5)
        for _ in range(publish_amount):
            module_target_sat.cli.ContentView.publish({'id': comp_content_view['id']})
        comp_content_view = module_target_sat.cli.ContentView.info({'id': comp_content_view['id']})
        assert len(comp_content_view['versions']) == publish_amount

    @pytest.mark.tier2
    def test_positive_promote_with_docker_repo(
        self, module_org, module_lce, content_view, module_target_sat
    ):
        """Add Docker-type repository to content view and publish it.
        Then promote it to the next available lifecycle-environment.

        :id: a7df98f4-0ec0-40f6-8941-3dbb776d47b9

        :expectedresults: Docker-type repository is promoted to content view
            found in the specific lifecycle-environment.
        """
        module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        assert len(content_view['versions']) == 1

        cvv = module_target_sat.cli.ContentView.version_info(
            {'id': content_view['versions'][0]['id']}
        )
        assert len(cvv['lifecycle-environments']) == 1

        module_target_sat.cli.ContentView.version_promote(
            {'id': cvv['id'], 'to-lifecycle-environment-id': module_lce.id}
        )
        cvv = module_target_sat.cli.ContentView.version_info(
            {'id': content_view['versions'][0]['id']}
        )
        assert len(cvv['lifecycle-environments']) == 2

    @pytest.mark.tier2
    @pytest.mark.upgrade
    def test_positive_promote_multiple_with_docker_repo(
        self, module_org, content_view, module_target_sat
    ):
        """Add Docker-type repository to content view and publish it.
        Then promote it to multiple available lifecycle-environments.

        :id: e9432bc4-a709-44d7-8e1d-00ca466aa32d

        :expectedresults: Docker-type repository is promoted to content view
            found in the specific lifecycle-environments.
        """
        module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        assert len(content_view['versions']) == 1

        cvv = module_target_sat.cli.ContentView.version_info(
            {'id': content_view['versions'][0]['id']}
        )
        assert len(cvv['lifecycle-environments']) == 1

        lces = [
            module_target_sat.cli_factory.make_lifecycle_environment(
                {'organization-id': module_org.id}
            )
            for _ in range(1, randint(3, 6))
        ]

        for expected_lces, lce in enumerate(lces, start=2):
            module_target_sat.cli.ContentView.version_promote(
                {'id': cvv['id'], 'to-lifecycle-environment-id': lce['id']}
            )
            cvv = module_target_sat.cli.ContentView.version_info({'id': cvv['id']})
            assert len(cvv['lifecycle-environments']) == expected_lces

    @pytest.mark.tier2
    def test_positive_promote_with_docker_repo_composite(
        self, module_org, module_lce, content_view, module_target_sat
    ):
        """Add Docker-type repository to composite content view and publish it.
        Then promote it to the next available lifecycle-environment.

        :id: fb7d132e-d7fa-4890-a0ec-746dd093513e

        :expectedresults: Docker-type repository is promoted to content view
            found in the specific lifecycle-environment.

        :BZ: 1359665
        """
        module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        assert len(content_view['versions']) == 1

        comp_content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': True, 'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.update(
            {
                'component-ids': content_view['versions'][0]['id'],
                'id': comp_content_view['id'],
            }
        )
        comp_content_view = module_target_sat.cli.ContentView.info({'id': comp_content_view['id']})
        assert content_view['versions'][0]['id'] in [
            component['id'] for component in comp_content_view['components']
        ]

        module_target_sat.cli.ContentView.publish({'id': comp_content_view['id']})
        comp_content_view = module_target_sat.cli.ContentView.info({'id': comp_content_view['id']})
        cvv = module_target_sat.cli.ContentView.version_info(
            {'id': comp_content_view['versions'][0]['id']}
        )
        assert len(cvv['lifecycle-environments']) == 1

        module_target_sat.cli.ContentView.version_promote(
            {
                'id': comp_content_view['versions'][0]['id'],
                'to-lifecycle-environment-id': module_lce.id,
            }
        )
        cvv = module_target_sat.cli.ContentView.version_info(
            {'id': comp_content_view['versions'][0]['id']}
        )
        assert len(cvv['lifecycle-environments']) == 2

    @pytest.mark.tier2
    @pytest.mark.upgrade
    def test_positive_promote_multiple_with_docker_repo_composite(
        self, content_view, module_org, module_target_sat
    ):
        """Add Docker-type repository to composite content view and publish it.
        Then promote it to the multiple available lifecycle-environments.

        :id: 345288d6-581b-4c07-8062-e58cb6343f1b

        :expectedresults: Docker-type repository is promoted to content view
            found in the specific lifecycle-environments.

        :BZ: 1359665
        """
        module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        assert len(content_view['versions']) == 1

        comp_content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': True, 'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.update(
            {
                'component-ids': content_view['versions'][0]['id'],
                'id': comp_content_view['id'],
            }
        )
        comp_content_view = module_target_sat.cli.ContentView.info({'id': comp_content_view['id']})
        assert content_view['versions'][0]['id'] in [
            component['id'] for component in comp_content_view['components']
        ]

        module_target_sat.cli.ContentView.publish({'id': comp_content_view['id']})
        comp_content_view = module_target_sat.cli.ContentView.info({'id': comp_content_view['id']})
        cvv = module_target_sat.cli.ContentView.version_info(
            {'id': comp_content_view['versions'][0]['id']}
        )
        assert len(cvv['lifecycle-environments']) == 1

        lces = [
            module_target_sat.cli_factory.make_lifecycle_environment(
                {'organization-id': module_org.id}
            )
            for _ in range(1, randint(3, 6))
        ]

        for expected_lces, lce in enumerate(lces, start=2):
            module_target_sat.cli.ContentView.version_promote(
                {
                    'id': cvv['id'],
                    'to-lifecycle-environment-id': lce['id'],
                }
            )
            cvv = module_target_sat.cli.ContentView.version_info({'id': cvv['id']})
            assert len(cvv['lifecycle-environments']) == expected_lces

    @pytest.mark.tier2
    @pytest.mark.upgrade
    def test_positive_name_pattern_change(self, module_org, module_target_sat):
        """Promote content view with Docker repository to lifecycle environment.
        Change registry name pattern for that environment. Verify that repository
        name on product changed according to new pattern.

        :id: 63c99ae7-238b-40ed-8cc1-d847eb4e6d65

        :expectedresults: Container repository name is changed
            according to new pattern.
        """
        lce = module_target_sat.cli_factory.make_lifecycle_environment(
            {'organization-id': module_org.id}
        )
        pattern_prefix = gen_string('alpha', 5)
        docker_upstream_name = 'hello-world'
        new_pattern = (
            f'{pattern_prefix}-<%= content_view.label %>/<%= repository.docker_upstream_name %>'
        )

        repo = _repo(
            module_target_sat,
            module_target_sat.cli_factory.make_product_wait({'organization-id': module_org.id})[
                'id'
            ],
            name=gen_string('alpha', 5),
            upstream_name=docker_upstream_name,
        )
        module_target_sat.cli.Repository.synchronize({'id': repo['id']})
        content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': False, 'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.add_repository(
            {'id': content_view['id'], 'repository-id': repo['id']}
        )
        module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})

        module_target_sat.cli.ContentView.version_promote(
            {'id': content_view['versions'][0]['id'], 'to-lifecycle-environment-id': lce['id']}
        )
        module_target_sat.cli.LifecycleEnvironment.update(
            {
                'registry-name-pattern': new_pattern,
                'id': lce['id'],
                'organization-id': module_org.id,
            }
        )
        lce = module_target_sat.cli.LifecycleEnvironment.info(
            {'id': lce['id'], 'organization-id': module_org.id}
        )
        assert lce['registry-name-pattern'] == new_pattern

        repo = module_target_sat.cli.Repository.list(
            {'name': repo['name'], 'environment-id': lce['id'], 'organization-id': module_org.id}
        )[0]
        expected_name = f'{pattern_prefix}-{content_view["label"]}/{docker_upstream_name}'.lower()
        assert (
            module_target_sat.cli.Repository.info({'id': repo['id']})['container-repository-name']
            == expected_name
        )

    @pytest.mark.tier2
    def test_positive_product_name_change_after_promotion(self, module_org, module_target_sat):
        """Promote content view with Docker repository to lifecycle environment.
        Change product name. Verify that repository name on product changed
        according to new pattern.

        :id: 92279755-717c-415c-88b6-4cc1202072e2

        :expectedresults: Container repository name is changed
            according to new pattern.
        """
        old_prod_name = gen_string('alpha', 5)
        new_prod_name = gen_string('alpha', 5)
        docker_upstream_name = 'hello-world'
        new_pattern = '<%= content_view.label %>/<%= product.name %>'

        lce = module_target_sat.cli_factory.make_lifecycle_environment(
            {'organization-id': module_org.id}
        )
        prod = module_target_sat.cli_factory.make_product_wait(
            {'organization-id': module_org.id, 'name': old_prod_name}
        )
        repo = _repo(
            module_target_sat,
            prod['id'],
            name=gen_string('alpha', 5),
            upstream_name=docker_upstream_name,
        )
        module_target_sat.cli.Repository.synchronize({'id': repo['id']})
        content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': False, 'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.add_repository(
            {'id': content_view['id'], 'repository-id': repo['id']}
        )
        module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        module_target_sat.cli.LifecycleEnvironment.update(
            {
                'registry-name-pattern': new_pattern,
                'id': lce['id'],
                'organization-id': module_org.id,
            }
        )
        lce = module_target_sat.cli.LifecycleEnvironment.info(
            {'id': lce['id'], 'organization-id': module_org.id}
        )
        assert lce['registry-name-pattern'] == new_pattern

        module_target_sat.cli.ContentView.version_promote(
            {'id': content_view['versions'][0]['id'], 'to-lifecycle-environment-id': lce['id']}
        )
        module_target_sat.cli.Product.update({'name': new_prod_name, 'id': prod['id']})

        repo = module_target_sat.cli.Repository.list(
            {'name': repo['name'], 'environment-id': lce['id'], 'organization-id': module_org.id}
        )[0]
        expected_name = f'{content_view["label"]}/{old_prod_name}'.lower()
        assert (
            module_target_sat.cli.Repository.info({'id': repo['id']})['container-repository-name']
            == expected_name
        )

        module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        module_target_sat.cli.ContentView.version_promote(
            {
                'id': content_view['versions'][-1]['id'],
                'to-lifecycle-environment-id': lce['id'],
            }
        )

        repo = module_target_sat.cli.Repository.list(
            {
                'name': repo['name'],
                'environment-id': lce['id'],
                'organization-id': module_org.id,
            }
        )[0]
        expected_name = f'{content_view["label"]}/{new_prod_name}'.lower()
        assert (
            module_target_sat.cli.Repository.info({'id': repo['id']})['container-repository-name']
            == expected_name
        )

    @pytest.mark.tier2
    def test_positive_repo_name_change_after_promotion(self, module_org, module_target_sat):
        """Promote content view with Docker repository to lifecycle environment.
        Change repository name. Verify that Docker repository name on product
        changed according to new pattern.

        :id: f094baab-e823-47e0-939d-bd0d88eb1538

        :expectedresults: Container repository name is changed
            according to new pattern.
        """
        old_repo_name = gen_string('alpha', 5)
        new_repo_name = gen_string('alpha', 5)
        docker_upstream_name = 'hello-world'
        new_pattern = '<%= content_view.label %>/<%= repository.name %>'

        lce = module_target_sat.cli_factory.make_lifecycle_environment(
            {'organization-id': module_org.id}
        )
        prod = module_target_sat.cli_factory.make_product_wait({'organization-id': module_org.id})
        repo = _repo(
            module_target_sat, prod['id'], name=old_repo_name, upstream_name=docker_upstream_name
        )
        module_target_sat.cli.Repository.synchronize({'id': repo['id']})
        content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': False, 'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.add_repository(
            {'id': content_view['id'], 'repository-id': repo['id']}
        )
        module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        module_target_sat.cli.LifecycleEnvironment.update(
            {
                'registry-name-pattern': new_pattern,
                'id': lce['id'],
                'organization-id': module_org.id,
            }
        )
        module_target_sat.cli.ContentView.version_promote(
            {'id': content_view['versions'][0]['id'], 'to-lifecycle-environment-id': lce['id']}
        )
        module_target_sat.cli.Repository.update(
            {'name': new_repo_name, 'id': repo['id'], 'product-id': prod['id']}
        )

        repo = module_target_sat.cli.Repository.list(
            {
                'name': new_repo_name,
                'environment-id': lce['id'],
                'organization-id': module_org.id,
            }
        )[0]
        expected_name = f'{content_view["label"]}/{old_repo_name}'.lower()
        assert (
            module_target_sat.cli.Repository.info({'id': repo['id']})['container-repository-name']
            == expected_name
        )

        module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        module_target_sat.cli.ContentView.version_promote(
            {
                'id': content_view['versions'][-1]['id'],
                'to-lifecycle-environment-id': lce['id'],
            }
        )

        repo = module_target_sat.cli.Repository.list(
            {
                'name': new_repo_name,
                'environment-id': lce['id'],
                'organization-id': module_org.id,
            }
        )[0]
        expected_name = f'{content_view["label"]}/{new_repo_name}'.lower()
        assert (
            module_target_sat.cli.Repository.info({'id': repo['id']})['container-repository-name']
            == expected_name
        )

    @pytest.mark.tier2
    def test_negative_set_non_unique_name_pattern_and_promote(self, module_org, module_target_sat):
        """Set registry name pattern to one that does not guarantee uniqueness.
        Try to promote content view with multiple Docker repositories to
        lifecycle environment. Verify that content has not been promoted.

        :id: eaf5e7ac-93c9-46c6-b538-4d6bd73ab9fc

        :expectedresults: Content view is not promoted
        """
        docker_upstream_names = ['hello-world', 'alpine']
        new_pattern = '<%= organization.label %>'

        lce = module_target_sat.cli_factory.make_lifecycle_environment(
            {'organization-id': module_org.id, 'registry-name-pattern': new_pattern}
        )

        prod = module_target_sat.cli_factory.make_product_wait({'organization-id': module_org.id})
        content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': False, 'organization-id': module_org.id}
        )
        for docker_name in docker_upstream_names:
            repo = _repo(module_target_sat, prod['id'], upstream_name=docker_name)
            module_target_sat.cli.Repository.synchronize({'id': repo['id']})
            module_target_sat.cli.ContentView.add_repository(
                {'id': content_view['id'], 'repository-id': repo['id']}
            )
        module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})

        with pytest.raises(CLIReturnCodeError):
            module_target_sat.cli.ContentView.version_promote(
                {'id': content_view['versions'][0]['id'], 'to-lifecycle-environment-id': lce['id']}
            )

    @pytest.mark.tier2
    def test_negative_promote_and_set_non_unique_name_pattern(
        self, module_org, module_product, module_target_sat
    ):
        """Promote content view with multiple Docker repositories to
        lifecycle environment. Set registry name pattern to one that
        does not guarantee uniqueness. Verify that pattern has not been
        changed.

        :id: 9f952224-084f-48d1-b2ea-85f3621becea

        :expectedresults: Registry name pattern is not changed
        """
        docker_upstream_names = ['hello-world', 'alpine']
        new_pattern = '<%= organization.label %>'

        content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': False, 'organization-id': module_org.id}
        )
        for docker_name in docker_upstream_names:
            repo = _repo(module_target_sat, module_product.id, upstream_name=docker_name)
            module_target_sat.cli.Repository.synchronize({'id': repo['id']})
            module_target_sat.cli.ContentView.add_repository(
                {'id': content_view['id'], 'repository-id': repo['id']}
            )
        module_target_sat.cli.ContentView.publish({'id': content_view['id']})
        content_view = module_target_sat.cli.ContentView.info({'id': content_view['id']})
        lce = module_target_sat.cli_factory.make_lifecycle_environment(
            {'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.version_promote(
            {'id': content_view['versions'][0]['id'], 'to-lifecycle-environment-id': lce['id']}
        )

        with pytest.raises(CLIReturnCodeError):
            module_target_sat.cli.LifecycleEnvironment.update(
                {
                    'registry-name-pattern': new_pattern,
                    'id': lce['id'],
                    'organization-id': module_org.id,
                }
            )


class TestDockerActivationKey:
    """Tests specific to adding ``Docker`` repositories to Activation Keys.

    :CaseComponent: ActivationKeys

    :team: Phoenix-subscriptions
    """

    @pytest.mark.tier2
    def test_positive_add_docker_repo_cv(
        self, module_org, module_lce, content_view_promote, module_target_sat
    ):
        """Add Docker-type repository to a non-composite content view
        and publish it. Then create an activation key and associate it with the
        Docker content view.

        :id: bb128642-d39f-45c2-aa69-a4776ea536a2

        :expectedresults: Docker-based content view can be added to activation
            key
        """
        activation_key = module_target_sat.cli_factory.make_activation_key(
            {
                'content-view-id': content_view_promote['content-view-id'],
                'lifecycle-environment-id': module_lce.id,
                'organization-id': module_org.id,
            }
        )
        assert activation_key['content-view'] == content_view_promote['content-view-name']

    @pytest.mark.tier2
    def test_positive_remove_docker_repo_cv(
        self, module_org, module_lce, content_view_promote, module_target_sat
    ):
        """Add Docker-type repository to a non-composite content view
        and publish it. Create an activation key and associate it with the
        Docker content view. Then remove this content view from the activation
        key.

        :id: d696e5fe-1818-46ce-9499-924c96e1ef88

        :expectedresults: Docker-based content view can be added and then
            removed from the activation key.
        """
        activation_key = module_target_sat.cli_factory.make_activation_key(
            {
                'content-view-id': content_view_promote['content-view-id'],
                'lifecycle-environment-id': module_lce.id,
                'organization-id': module_org.id,
            }
        )
        assert activation_key['content-view'] == content_view_promote['content-view-name']

        # Create another content view replace with
        another_cv = module_target_sat.cli_factory.make_content_view(
            {'composite': False, 'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.publish({'id': another_cv['id']})
        another_cv = module_target_sat.cli.ContentView.info({'id': another_cv['id']})
        module_target_sat.cli.ContentView.version_promote(
            {'id': another_cv['versions'][0]['id'], 'to-lifecycle-environment-id': module_lce.id}
        )

        module_target_sat.cli.ActivationKey.update(
            {
                'id': activation_key['id'],
                'organization-id': module_org.id,
                'content-view-id': another_cv['id'],
                'lifecycle-environment-id': module_lce.id,
            }
        )
        activation_key = module_target_sat.cli.ActivationKey.info({'id': activation_key['id']})
        assert activation_key['content-view'] != content_view_promote['content-view-name']

    @pytest.mark.tier2
    def test_positive_add_docker_repo_ccv(
        self, module_org, module_lce, content_view_publish, module_target_sat
    ):
        """Add Docker-type repository to a non-composite content view
        and publish it. Then add this content view to a composite content view
        and publish it. Create an activation key and associate it with the
        composite Docker content view.

        :id: 1d9b82fd-8dab-4fd9-ad35-656d712d56a2

        :expectedresults: Docker-based content view can be added to activation
            key

        :BZ: 1359665
        """
        comp_content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': True, 'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.update(
            {
                'component-ids': content_view_publish['id'],
                'id': comp_content_view['id'],
            }
        )
        comp_content_view = module_target_sat.cli.ContentView.info({'id': comp_content_view['id']})
        assert content_view_publish['id'] in [
            component['id'] for component in comp_content_view['components']
        ]

        module_target_sat.cli.ContentView.publish({'id': comp_content_view['id']})
        comp_content_view = module_target_sat.cli.ContentView.info({'id': comp_content_view['id']})
        comp_cvv = module_target_sat.cli.ContentView.version_info(
            {'id': comp_content_view['versions'][0]['id']}
        )
        module_target_sat.cli.ContentView.version_promote(
            {'id': comp_cvv['id'], 'to-lifecycle-environment-id': module_lce.id}
        )
        activation_key = module_target_sat.cli_factory.make_activation_key(
            {
                'content-view-id': comp_content_view['id'],
                'lifecycle-environment-id': module_lce.id,
                'organization-id': module_org.id,
            }
        )
        assert activation_key['content-view'] == comp_content_view['name']

    @pytest.mark.tier2
    def test_positive_remove_docker_repo_ccv(
        self, module_org, module_lce, content_view_publish, module_target_sat
    ):
        """Add Docker-type repository to a non-composite content view
        and publish it. Then add this content view to a composite content view
        and publish it. Create an activation key and associate it with the
        composite Docker content view. Then, remove the composite content view
        from the activation key.

        :id: b4e63537-d3a8-4afa-8e18-57052b93fb4c

        :expectedresults: Docker-based composite content view can be added and
            then removed from the activation key.

        :BZ: 1359665
        """
        comp_content_view = module_target_sat.cli_factory.make_content_view(
            {'composite': True, 'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.update(
            {
                'component-ids': content_view_publish['id'],
                'id': comp_content_view['id'],
            }
        )
        comp_content_view = module_target_sat.cli.ContentView.info({'id': comp_content_view['id']})
        assert content_view_publish['id'] in [
            component['id'] for component in comp_content_view['components']
        ]

        module_target_sat.cli.ContentView.publish({'id': comp_content_view['id']})
        comp_content_view = module_target_sat.cli.ContentView.info({'id': comp_content_view['id']})
        comp_cvv = module_target_sat.cli.ContentView.version_info(
            {'id': comp_content_view['versions'][0]['id']}
        )
        module_target_sat.cli.ContentView.version_promote(
            {'id': comp_cvv['id'], 'to-lifecycle-environment-id': module_lce.id}
        )
        activation_key = module_target_sat.cli_factory.make_activation_key(
            {
                'content-view-id': comp_content_view['id'],
                'lifecycle-environment-id': module_lce.id,
                'organization-id': module_org.id,
            }
        )
        assert activation_key['content-view'] == comp_content_view['name']

        # Create another content view replace with
        another_cv = module_target_sat.cli_factory.make_content_view(
            {'composite': False, 'organization-id': module_org.id}
        )
        module_target_sat.cli.ContentView.publish({'id': another_cv['id']})
        another_cv = module_target_sat.cli.ContentView.info({'id': another_cv['id']})
        module_target_sat.cli.ContentView.version_promote(
            {'id': another_cv['versions'][0]['id'], 'to-lifecycle-environment-id': module_lce.id}
        )

        module_target_sat.cli.ActivationKey.update(
            {
                'id': activation_key['id'],
                'organization-id': module_org.id,
                'content-view-id': another_cv['id'],
                'lifecycle-environment-id': module_lce.id,
            }
        )
        activation_key = module_target_sat.cli.ActivationKey.info({'id': activation_key['id']})
        assert activation_key['content-view'] != comp_content_view['name']


class TestPodman:
    """Tests specific to using podman push/pull on Satellite

    :CaseComponent: Podman

    :team: Phoenix-content
    """

    @pytest.fixture(scope='class')
    def enable_podman(module_product, module_target_sat):
        """Enable base_os and appstream repos on the sat through cdn registration and install podman.
        Also includes a change to the katello.yaml file, and a restart of foreman"""
        module_target_sat.register_to_cdn()
        if module_target_sat.os_version.major > 7:
            module_target_sat.enable_repo(module_target_sat.REPOS['rhel_bos']['id'])
            module_target_sat.enable_repo(module_target_sat.REPOS['rhel_aps']['id'])
        else:
            module_target_sat.enable_repo(module_target_sat.REPOS['rhscl']['id'])
            module_target_sat.enable_repo(module_target_sat.REPOS['rhel']['id'])
        result = module_target_sat.execute(
            'dnf install -y --disableplugin=foreman-protector podman'
        )
        assert result.status == 0
        result = module_target_sat.execute(
            r"sed -i '/:katello:/a\ \ :container_image_registry:\n    :allow_push: true\n' /etc/foreman/plugins/katello.yaml"
        )
        assert result.status == 0
        result = module_target_sat.execute('foreman-maintain service restart --only foreman')
        assert result.status == 0

    @pytest.mark.tier2
    def test_podman_push(self, module_target_sat, module_product, enable_podman):
        """Push a small and large container image to Pulp

        :id: 488adc49-899e-4739-8bca-0cd255da63ae

        :steps:
            1. Using the enable_podman fixture, enable both base_os and appstream repos and install
            podman on satellite.
            2. Using podman, pull a small and large image from the fedoraproject registry
            3. Push both images to pulp

        :expectedresults: A docker repository is created for both images, with a valid version id.

        :CaseImportance: High
        """
        result = module_target_sat.execute('podman pull registry.fedoraproject.org/arianna')
        assert result.status == 0
        result = module_target_sat.execute('podman pull registry.fedoraproject.org/fedora')
        assert result.status == 0
        small_image_id = module_target_sat.execute('podman images arianna -q')
        assert small_image_id
        large_image_id = module_target_sat.execute('podman images fedora -q')
        assert small_image_id
        podman_cmd = f'podman push --creds admin:changeme {small_image_id.stdout.strip()} {module_target_sat.hostname}/arianna'
        result = module_target_sat.execute(podman_cmd)
        module_target_sat.execute(
            f'podman push --creds admin:changeme {large_image_id.stdout.strip()} {module_target_sat.hostname}/arianna'
        )
        module_target_sat.execute('pulp container repository -t push list')
