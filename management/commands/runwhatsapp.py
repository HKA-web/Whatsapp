import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand
from whatsapp import settings

logger = logging.getLogger(__name__)
cwd = Path(__file__).resolve().parent.parent.parent

def flatten_dict(d, parent_key='', sep='_'):
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}".upper() if parent_key else k.upper()
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        elif isinstance(v, list):
            items[new_key] = json.dumps(v)
        else:
            items[new_key] = str(v)
    return items


class Command(BaseCommand):
    help = 'Management command to run whatsapp api server'

    def add_arguments(self, parser):
        parser.add_argument(
            '--engine',
            type=str,
            choices=['baileys', 'whatsmeow'],
            default='baileys',
            help='Pilih engine WhatsApp yang akan dijalankan (default: baileys)',
        )

    def handle(self, *args, **kwargs):
        engine = (kwargs.get('engine') or 'baileys').lower()
        self.stdout.write(f'''{os.linesep}>> {self.help} (Engine: {engine}) <<{os.linesep}{os.linesep}''')
        try:
            merged_settings = {}
            for key in dir(settings):
                if key.isupper():
                    merged_settings[key] = getattr(settings, key)
            if hasattr(settings, 'YAML_OVERRIDE'):
                merged_settings.update(settings.YAML_OVERRIDE)

            env_for_node = flatten_dict(merged_settings)
            for k, v in env_for_node.items():
                os.environ[k] = v

            parameter = [
                f'''--port={settings.PORT}''',
                f'''--webhook.url={settings.WEBHOOK_URL}''',
            ]
            from urllib.parse import urlparse, quote_plus
            uri = urlparse(settings.WEBHOOK_URL)
            http_scheme = 'https' if uri.scheme == 'wss' else ('http' if uri.scheme in ('ws', '') else uri.scheme)
            parameter.append(f'''--catalogI18n={http_scheme}://{uri.netloc}/i18n.json''')

            if settings.CONFIG:
                if isinstance(settings.CONFIG, dict):
                    if settings.SESSION and os.path.exists(settings.SESSION):
                        if os.path.isfile(settings.SESSION):
                            output = os.path.join(os.path.dirname(settings.SESSION), 'patch.config.json')
                        else:
                            output = os.path.join(settings.SESSION, 'patch.config.json')
                    else:
                        output = tempfile.TemporaryFile()
                    with open(output, 'w') as config:
                        json.dump(settings.CONFIG, config, indent=4)
                    parameter.append(f'''--config={output}''')
                elif os.path.exists(settings.CONFIG):
                    if os.path.isfile(settings.CONFIG):
                        parameter.append(f'''--config={settings.CONFIG}''')
                    else:
                        self.stdout.write('Settings \'WHATSAPP_CONFIG\' config must file.json not directory')
                else:
                    self.stdout.write('Settings \'WHATSAPP_CONFIG\' config must file.json or string.json')

            if engine == 'whatsmeow':
                wa_db = settings.djangosettings.DATABASES.get('WHATSAPP') or settings.djangosettings.DATABASES.get('default', {})
                db_user = quote_plus(str(wa_db.get('USER', 'postgres')))
                db_pass = quote_plus(str(wa_db.get('PASSWORD', 'toor')))
                db_host = wa_db.get('HOST', '127.0.0.1')
                db_port = wa_db.get('PORT', 5432)
                db_name = wa_db.get('NAME', 'microservice')
                pg_dsn = f"postgres://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}?sslmode=disable&search_path=public"
                os.environ['WHATSAPP_PG_DSN'] = pg_dsn
                parameter.append(f'''--dsn={pg_dsn}''')

                whatsmeow_dir = os.path.join(cwd, 'engine', 'whatsmeow')
                whatsmeow_exe = os.path.join(whatsmeow_dir, 'whatsmeow.exe' if os.name == 'nt' else 'whatsmeow')
                go_bin = os.path.join(settings.djangosettings.BASE_DIR.absolute(), 'bin', 'go', 'bin', 'go.exe' if os.name == 'nt' else 'go')
                if not os.path.exists(go_bin):
                    go_bin = 'go'

                if settings.djangosettings.DEBUG or not os.path.exists(whatsmeow_exe):
                    build_cmd = f'"{go_bin}" build -o "{whatsmeow_exe}" ./cmd/server'
                    self.stdout.write(f'Building whatsmeow: {build_cmd}')
                    subprocess.check_call(build_cmd, env=os.environ, cwd=whatsmeow_dir, shell=True)

                command = f'"{whatsmeow_exe}" {" ".join(parameter)}'
                run_cwd = whatsmeow_dir
            else:
                command = f'''yarn start {' '.join(parameter)}'''
                if settings.djangosettings.DEBUG:
                    command = f'''yarn start:nodemon {' '.join(parameter)}'''
                run_cwd = cwd

            logger.info('Call %s', command)

            process = subprocess.Popen(
                command,
                env=os.environ,
                cwd=run_cwd,
                shell=True,
            )

            with open(
                os.path.join(
                    settings.djangosettings.BASE_DIR.absolute(),
                    f'data/{os.path.splitext(os.path.basename(__file__))[0]}.pid'
                ),
                'w'
            ) as pid:
                pid.write(str(process.pid))

            process.wait()


        except (KeyboardInterrupt,) as e:
            self.stdout.write('Stop whatsapp api server')
            logger.exception(e)
        except (Exception,) as e:
            self.stdout.write(f'Whatsapp api server can''t be run, {e}')
            logger.exception(e)
        else:
            # process.stdout.close()
            code = process.wait()
            if code:
                raise subprocess.CalledProcessError(code, 'Whatsapp api server run')
