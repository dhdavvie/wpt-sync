# Setup

## Dev environment

Setting up a development environment
requires [Docker](https://www.docker.com/). 

__See section below about using docker-compose.__

We're somewhat following [mozilla-services' Dockerflow](https://github.com/mozilla-services/Dockerflow).

From repo root:

```
docker build -t wptsync_dev --add-host=rabbitmq:127.0.0.1 --file wpt-sync/docker/dev/Dockerfile .
```

The above sets the vct repo root as the build context for an image called `wptsync_dev`

To start all the services in the container:

```
# in project root dir
docker run -it --init --name wptsync_test --env WPTSYNC_CREDS=/app/.../credentials.ini \
--mount type=bind,source=$(pwd),target=/app/vct \
--mount type=bind,source=$(pwd)/../temp,target=/app/repos \
--mount type=bind,source=$(pwd)/wpt-sync/workspace,target=/app/workspace \
--mount type=bind,source=$(pwd)/wpt-sync/appdata,target=/app/data wptsync_dev
```

This runs the script designated by ENTRYPOINT in the Dockerfile with an init process. You could use `--env-file` instead of `--env` to set environment variables in the container. 

Stop it with:

```
docker stop [container name]
```

You can see names of running containers with `docker container ls`.

If you want to run a different command in the container
interactively, use the `-i` and `--entrypoint` options like:


```
# in project root dir
docker run -it --env WPTSYNC_REPO_ROOT=/app/vct/wpt-sync/test/testdata \
    --mount type=bind,source=$(pwd),target=/app/vct \
    --entrypoint "/app/venv/bin/pytest" wptsync_dev
```

You can pass additional flags to the entrypoint after the `wptsync_dev` part, like `... --entrypoint "/app/venv/bin/pytest" wptsync_dev -x`

### Volumes to --mount

See the VOLUMES directive in the Dockerfile for information about what
volumes it's expecting. 

### Permissions

Inside the Docker container we run as the app user with uid 10001. This user
requires write permissions to directories `repos`, `work`, `logs` and
`data`. 

For each path, run

```
sudo chown -R 10001 <path>
```

You may not need to do this at all on mac.

### Using docker-compose

The docker-compose.yml file is provided as a convenience in the dev environment and it uses the same Dockerfile referenced in previous instructions.

There are instructions in the docker-compose.yml file about how to customize
your dev environment with appropriate mounts.

From wpt-sync dir you can run:

```
docker-compose build
```

Then to start the services with the default entrypoint (pulse listener):

```
docker-compose up
```

To run an alternate command, e.g. bash, instead of the default entrypoint:

```
docker-compose run --entrypoint bash sync
```

Another example (__running tests__):

```
docker-compose run -e WPTSYNC_REPO_ROOT=/app/vct/wpt-sync/test/testdata --entrypoint /app/venv/bin/pytest sync test
```

You can also see an alternate way to run tests without docker-compose in `.travis.yml`.

__Note__ that replacing the default entrypoint means that you're nolonger running the `start_wptsync.sh` script at container start-up and therefore some
configuration may be missing or incomplete. (For example, the Dockerfile (build-time) doesn't set up any credentials; instead, credentials are only set up in the container at run-time with the above-mentioned script.)

# Deployment (deprecated)

The deployment steps are configured in an ansible role in `ansible/roles/wptsync`. The entry point is the playbook `ansible/wptsync-deploy`. It assumes the services are being deployed to a minimal Centos 7 system.

In the near future, we want to [handle credentials differently](http://mozilla-version-control-tools.readthedocs.io/en/latest/vcssync/servo.html#provisioning-a-new-instance) 
(with ansible vault), but to test the deployment locally you can fill in the ini files in
`ansible/roles/wptsync/templates/`. Other configuration of interest is in
`ansible/roles/wptsync/defaults/main.yml`. 

You will also need to specify which host(s) to deploy to in `ansible/hosts`
under `[wptsync]`

## Running the playbook

If you're working in an __hg clone__ of version-control-tools:

*   Create venv in repo root. This installs ansible, among other things.
    You may need to temporarily remove 
    git-cinnabar from your PATH for this to work because of a name clash
    with "configure".

    ```
    ./create-deploy-environment
    ```

*   Activate the venv

    ```
    source venv/bin/activate
    ```


*   Run the ansible playbook (ansible/wptsync-deploy.yml)
    ```
    ./deploy wptsync
    ```

If you're in a __git clone__ of version-control-tools:

*   Create venv in repo root. 
    You may need to temporarily remove 
    git-cinnabar from your PATH for this to work because of a name clash
    with "configure".

    ```
    ./create-deploy-environment
    ```

*   Activate the venv
    ```
    source venv/bin/activate
    ```

* Set the `vct` variable in `ansible/group_vars/all` to be the path to your repo root

* Run `ansible-playbook -i ansible/hosts -f 20 ansible/wptsync-deploy.yml -vvv`

## Checking the services

The ansible playbook starts a few systemd units grouped together under
`wptsync.target` and `wptcelery.target`, as well as the rabbitmq-server. 
Some useful commands to examine the services on the host:

* `systemctl stop|start wptsync.target` 
* `systemctl listunits | grep wpt`
* `journalctl -u wptsync-pulse-monitor.service`
* `systemctl status wptsync-celery-beat.service -l`

There are also log files to look at: `/home/wptsync/*.log`

# Implementation strategy

## Downstreaming

* Given an upstream PR

* Create a bug in a component determined by the files changed

* Wait until it is approved or the Travis status passes

* Create a local Try run based on mozilla-central for an artifact
  build + the changes, and run only tests that changed

* Update local metadata for the expectation changes.

* Run a stability checking run with --rebuild=10

* Use the results of this second try run to disable any obviously-unstable tests

* Repeat as required for new pushes to the PR (should reuse metadata
  but not disabled tests)

### Disaster Recovery

* Miss the PR opening
 - Should get later events with the PR; notice we don't have a record
   of it and start the sync process above.

* Miss the Travis status changing or the PR being approved
* PR is merged without a clean travis run or approval (by an
  admin).
  - Start the downstreaming process at the point the PR is merged.

* Rebasing the changes onto m-c causes a merge conflict.
 - This implies that we are upstreaming something that will also have
   a merge conflict.
 - One option is to fix on our upstreaming branch and then wait until
   we get a push that will rebase cleanly. But then we miss out on
   early metadata generation.
 - Could fix locally and continue the process, which would allow us
   to update metadata at the expense of double work (we may have to
   fix the conflict *again* when we deal with a push).
 - Maybe want a command to continue the process after manual rebase.

* Error on Try (e.g. build failed)
  - Manual rebase and repush? Maybe want a command for this so we
    update the task that we are waiting for

* Error updating metadata / disabling tests
  - Needs manual investigation and fixup. Might need to update the
    status of the sync to say we have metadata.

* Change breaks the runner
  - Need to notice that this happened. Probably need to make some
    local fixup and ensure that this is  upstreamed asap.

## Upstreaming

* See a push to mozilla-inbound or autoland touching
  testing/web-platform-tests

* Check all pushes since last merge to central to eliminate backouts

* If a previous sync push was backed out, close the related PR.

* Rebase the changes onto latest wpt-master (alternative: use last
  sync push. Means we shouldn't get rebase errors, but might get merge
  conflicts in the PR).

* Create a remote branch with the commits

* Create a PR for the remote branch and auto approve the commits

* Wait for the upstream CI to pass

* Wait for the change to land on m-c

* Merge the PR

* If commits land directly on m-c we start the
  process above, but for mozilla central, using the last incoming
  merge as the start point.

### Disaster Recovery

* Miss a push to mozilla-inbound, or don't process it before it's
  merged to central.
 - OK if we see another push before the next merge to central. Maybe
   instead of using the last merge to central, record the last
   upstream-landed sync commit. But we have problems if we see the
   same commits on autoland and inbound. Or use the pushlog to
   recover.

* Changes don't rebase cleanly onto upstream.
 - Need to fix this up at some point. Best option is probably to
   start on the same revision as we are synced at and if a rebase
   fails, open the PR based on the current sync commit and fix it
   upstream. Then use *those* commits when reapplying onto master,
   during push rather than just the local ones. There is still a race
   condition there of course (the faster syncs are, the less common
   this will be).




## Push

* On a timer, check if new commits have landed upstream.

* For each commit, map to the PR that generated it, if any

* Check if we have a sync for the PR that is completed (or
  upstream). If so mark the corresponding commits as importable

* Find the last commit such that all earlier commits are either
  already imported or importable.

* For each merge commit of a PR that is an ancestor-or-self of the
  last importable commit, copy the upstream tree corresponding to that
  commit over to the tip of mozilla-inbound.

* Apply any local changes that have not yet upstreamed.

* Apply any metadata changes for the PR.

* Update the test manifest.

* Land the changes in mozilla central.

### Disaster recovery

* Commits with no corresponding PR
 - Continue like normal. Should consider an extra metadata update
   cycle in this case, but defering that for now on the assumption
   that such commits are probably mostly fixing minor lint errors, not
   changing test expectations, and are rare enough that we can fixup
   inbound if required.

* Error applying unlanded upstream commits onto inbound.
 - Manual fixup. Need to be able to resume the process once this fixup
   is complete.

* Subsequent changes invalidate metadata update.

 - Initially assume this is rare and can be dealt with as fixups after
   landing. If the problem persists then consider running a metadata
   update step after finalising the set of commits (although there is
   obvously still a race condition here since that takes finite time
   to run).

# General problems

* GitHub is down
  - Retry tasks. This blocks many things, so just retrying everything
    should be fine. Maybe pause if we think this is happening?
  - We might miss many events related to PRs and merges. Once GH is back up 
    and we periodically land upstream changes, look at all new commits on 
    master since last landing and start new syncs for them as needed.
* Bugzilla is down
  - Retry? For in-progress syncs, maybe we can accumulate a backlog
    of bug comments that need to be posted. For new downstreaming syncs, we don't want to start the sync process without creating a bug first, so just retry.
* Trees are closed. 
  - Retry.

