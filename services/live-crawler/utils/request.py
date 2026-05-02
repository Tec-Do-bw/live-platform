import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class RequestSession:
    @staticmethod
    def get_session(retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 504)):
        session = requests.Session()
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session 