import urllib.request
import json

BASE = 'https://raw.githubusercontent.com'

class Resource:
    def __init__(self, url, save_dir):
        self.url = url
        self._file = url[url.rindex("/"):]
        self.filename = f'{save_dir}/{self._file}'

    def save(self):
        ''' Download and save. '''
        with (urllib.request.urlopen(self.url) as response,
              open(self.filename, 'wb') as save):
            save.write(response.read())


if __name__ == '__main__':
    with open('.resources') as resources:
        resource_list = json.load(resources)
        for resource in resource_list:
            repo = resource['repo']
            commit = resource['commit']
            out = resource['out']
            for path in resource['files']:
                Resource(f'{BASE}/{repo}/{commit}/{path}', out).save()
