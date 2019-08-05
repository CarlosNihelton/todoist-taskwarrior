# todoist-taskwarrior

A tool for syncing Todoist tasks with Taskwarrior.

## Installation

```bash
git clone https://git.webmeisterei.com/webmeisterei/todoist-taskwarrior.git
cd todoist-taskwarrior/
```

- To install in Virtualenv:

```bash
virtualenv -p /usr/bin/python3 venv
venv/bin/pip install -r requirements.txt
venv/bin/python setup.py install
```

- To install global:

```bash
sudo pip3 install -r requirements.txt
sudo python3 setup.py install
```

## Configure

First optain a Todoist API key from the [Todoist Integrations Settings](https://todoist.com/prefs/integrations).

Now you can configure `titwsync` with (replace `./venv/bin/titwsync` with `titwsync` if you use todoist_taskwarrior without a virtualenv):

```sh
./venv/bin/titwsync configure --map-project Inbox= --map-project Company=work --map-project Company.SubProject=work.subproject --map-tag books=reading <TODOIST_API_KEY>
```

`titwsync configure` writes the configuration to `~/.titwsyncrc.yaml`, with the key: `taskwarrior.project_sync.PROJECT_NAME` you can enable or disable the sync of a whole project!

## Usage

Running the tool requires that your Todoist API key is available from the
environment under the name `TODOIST_API_KEY`. The key can be found or created in
the ).

The main task is `sync` which will sync all tasks. Since Todoist's internal
ID is saved with the task, subsequent runs will detect and skip duplicates:

Replace `./venv/bin/titwsync` with `titwsync` if you use todoist_taskwarrior without a virtualenv.

```sh
./venv/bin/titwsync sync
```

## Development

### Testing

```sh
python -m pytest tests
```

## License

Licensed under the MIT license.

## Authors

- 2018-2019 [matt-snider](https://github.com/matt-snider/todoist-taskwarrior)
- 2019-     [webmeisterei](https://git.webmeisterei.com/webmeisterei/todoist-taskwarrior)