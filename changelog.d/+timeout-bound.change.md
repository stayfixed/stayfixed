The reusable workflow's `timeout-minutes` input is no longer held to 5–60 minutes, and a value
outside that range no longer fails the job's first step. The job runs under the value you pass, and
the platform's own job limit (360 minutes on a hosted runner) bounds it. A project whose gates need
more than an hour can now say so. The range protected nothing, because a pull request can edit the
calling file. A job that runs out of time is still cancelled, which is not a pass.
