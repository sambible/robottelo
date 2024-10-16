import re

import requests

from robottelo.cli.base import CLIReturnCodeError
from robottelo.host_helpers.cli_factory import CLIFactory


class ContentInfo:
    """Miscellaneous content helper methods"""

    def get_repo_files(self, repo_path, extension='rpm'):
        """Returns a list of repo files (for example rpms) in specific repository
        directory.

        :param str repo_path: unix path to the repo, e.g. '/var/lib/pulp/fooRepo/'
        :param str extension: extension of searched files. Defaults to 'rpm'
        :param str optional hostname: hostname or IP address of the remote host. If
            ``None`` the hostname will be get from ``main.server.hostname`` config.
        :return: list representing rpm package names
        :rtype: list
        """
        if not repo_path.endswith('/'):
            repo_path += '/'
        result = self.execute(
            f"find {repo_path} -name '*.{extension}' | awk -F/ '{{print $NF}}'",
        )
        if result.status != 0:
            raise CLIReturnCodeError(result.status, result.stderr, f'No .{extension} found')
        # strip empty lines and sort alphabetically (as order may be wrong because
        # of different paths)
        return sorted(repo_file for repo_file in result.stdout.splitlines() if repo_file)

    def get_repo_files_by_url(self, url, extension='rpm'):
        """Returns a list of repo files (for example rpms) in a specific repository
        published at some url.
        :param url: url where the repo or CV is published
        :param extension: extension of searched files. Defaults to 'rpm'
        :return:  list representing rpm package names
        """
        if not url.endswith('/'):
            url += '/'

        result = requests.get(url, verify=False)
        if result.status_code != 200:
            raise requests.HTTPError(f'{url} is not accessible')

        links = re.findall(r'(?<=href=").*?(?=">)', result.text)

        if 'Packages/' not in links:
            return sorted(line for line in links if extension in line)

        files = []
        subs = self.get_repo_files_by_url(f'{url}Packages/', extension='/')
        for sub in subs:
            files.extend(self.get_repo_files_by_url(f'{url}Packages/{sub}', extension))

        return sorted(files)

    def get_repomd(self, repo_url):
        """Fetches content of the repomd file of a repository

        :param repo_url: the 'Published_At' link of a repo
        :return: string with repomd content
        """
        repomd_path = 'repodata/repomd.xml'
        result = requests.get(f'{repo_url}/{repomd_path}', verify=False)
        if result.status_code != 200:
            raise requests.HTTPError(f'{repo_url}/{repomd_path} is not accessible')

        return result.text

    def get_repomd_revision(self, repo_url):
        """Fetches a revision of a repository.

        :param str repo_url: the 'Published_At' link of a repo
        :return: string containing repository revision
        :rtype: str
        """
        match = re.search('(?<=<revision>).*?(?=</revision>)', self.get_repomd(repo_url))
        if not match:
            raise ValueError(f'<revision> not found in repomd file of {repo_url}')

        return match.group(0)


class Factories:
    """Mixin that provides attributes for each factory type"""

    @property
    def cli_factory(self):
        if not getattr(self, '_cli_factory', None):
            self._cli_factory = CLIFactory(self)
        return self._cli_factory
