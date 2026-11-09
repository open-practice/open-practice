#!/usr/bin/env python3
"""Read-only external HTTPS checks. No credentials or third-party dependencies."""
import argparse, datetime, json, socket, ssl, urllib.request

DEFAULT_HOSTS = ['open-practice.open-practice.workers.dev', 'tapstall.zlnew.workers.dev', 'stpi-deskos.stpi-cloud.workers.dev']

def inspect(host):
    result = {'host': host, 'tls': {}, 'errors': []}
    for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
        try:
            context = ssl.create_default_context()
            context.minimum_version = context.maximum_version = version
            with socket.create_connection((host, 443), timeout=15) as connection:
                with context.wrap_socket(connection, server_hostname=host) as secure:
                    cert = secure.getpeercert()
                    result['tls'][version.name] = {'verified': True, 'cipher': secure.cipher()[0], 'expires': cert.get('notAfter'), 'dns_names': [value for kind, value in cert.get('subjectAltName', []) if kind == 'DNS']}
        except Exception as error:
            result['tls'][version.name] = {'verified': False, 'error': type(error).__name__ + ': ' + str(error)}
    try:
        request = urllib.request.Request('https://' + host + '/', headers={'User-Agent': 'Open-Practice-HTTPS-Check/1.0'})
        with urllib.request.urlopen(request, timeout=20) as response:
            result['http_status'] = response.status
            result['final_url'] = response.url
    except Exception as error:
        result['errors'].append(type(error).__name__ + ': ' + str(error))
    result['passed'] = result.get('http_status') == 200 and all(value['verified'] for value in result['tls'].values())
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hosts', nargs='*', default=DEFAULT_HOSTS)
    args = parser.parse_args()
    hosts = args.hosts or DEFAULT_HOSTS
    if any('/' in host or ':' in host or not host.endswith('.workers.dev') for host in hosts):
        parser.error('Supply bare workers.dev hostnames only, not URLs.')
    report = {'checked_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'scope': 'External observation from this machine; not proof of access on every client or network.', 'sites': [inspect(host) for host in hosts]}
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if all(site['passed'] for site in report['sites']) else 1)
