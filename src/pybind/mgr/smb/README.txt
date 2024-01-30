
This is the work in progress smb manager module.
This readme file should be deleted once some real docs exist,
prior to merging this code!

# CLI Interface

There are two ways interacting with the smb module. The traditional mode
uses commands like:
  ceph smb cluster create foo active-directory --domain-realm=foo.example.org --domain-join-user-pass=Administrator%Passw0rd
  ceph smb share create foo myshare1 --name='My Favorite Share' --cephfs-volume=cephfs --path=/my/stuff
and
  ceph smb share rm foo myshare1

The alternative is to use the `ceph smb apply` command to ingest declarative configuration
resources. This is inspired by the `ceph orch` workflow and `ceph nfs export apply`.

  ceph smb apply -i - <<EOF
  ---
  resource_type: ceph.smb.cluster
  cluster_id: foo
  auth_mode: active-directory
  domain_settings:
    realm: foo.example.com
    join_sources:
      - source_type: password
        auth:
          username: Administrator
          password: Passw0rd
  ---
  resource_type: ceph.smb.share
  cluster_id: foo
  share_id: myshare1
  cephfs:
    volume: cephfs
    path: /my/stuff
  EOF

To remove resources using the apply command, set the intent value to 'removed'.

  ceph smb apply -i - <<EOF
  ---
  resource_type: ceph.smb.share
  intent: removed
  cluster_id: foo
  share_id: myshare1
  EOF




# TODOs

#  validate share name is not used by a different share in same cluster
#  should cluster/share create cmmands be exclusive creates?

# Maybes
#  CMD: `smb join-auth create ...`
#  CMD: `smb join-ath rm ...`
#  CMD: `smb users-and-groups ...` (etc)
#  ^^^ could just require the use of  apply for these ops

## Done(ish)
#  cluster create
#  cluster rm
#  generate orch service spec
#  dump service-spec [cluster_id]
#  submit service spec to orch module
#  cephx entities for user access
#  validate names
#  validate remove allowed for cluster
#  validate remove allowed for join
#  validate remove allowed for ug
#  path resolver
