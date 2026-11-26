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

    def handle(self, *args, **kwargs):
        self.stdout.write(f'''{os.linesep}>> {self.help} <<{os.linesep}{os.linesep}''')
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
            from urllib.parse import urlparse
            parameter.append(f'''--catalogI18n={'{uri.scheme}://{uri.netloc}/'.format(uri=urlparse(settings.WEBHOOK_URL))}i18n.json''')

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

            command = f'''yarn start {' '.join(parameter)}'''
            if settings.djangosettings.DEBUG:
                command = f'''yarn start:nodemon {' '.join(parameter)}'''
            logger.info('Call %s', command)

            process = subprocess.Popen(
                command,
                env=os.environ,
                cwd=cwd,
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
