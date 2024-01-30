
This is the work in progress smb manager module.
This readme file should be deleted once some real docs exist,
prior to merging this code!


# CLI Interface

There are two ways interacting with the smb module using the `ceph` CLI
command. The traditional mode uses commands like:
```
  ceph smb cluster create foo active-directory --domain-realm=foo.example.org --domain-join-user-pass=Administrator%Passw0rd
  ceph smb share create foo myshare1 --share-name='My Favorite Share' --cephfs-volume=cephfs --path=/my/stuff
```
and

```
  ceph smb share rm foo myshare1
```

The alternative is to use the `ceph smb apply` command to ingest configuration
resources that use a declarative style. This is inspired by the `ceph orch`
workflow and `ceph nfs export apply`. Example:

```
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
```

To remove resources using the apply command, set the intent value to 'removed'.

```
  ceph smb apply -i - <<EOF
  ---
  resource_type: ceph.smb.share
  intent: removed
  cluster_id: foo
  share_id: myshare1
  EOF
```

There are four resource types:
* `ceph.smb.cluster`
* `ceph.smb.share`
* `ceph.smb.join.auth`
* `ceph.smb.usersgroups`

The `ceph.smb.cluster` resource type defines properties that impact an entire
cluster, even if that's a cluster of one node. This includes what domain the
cluster might belong to.

The `ceph.smb.share` resource type defines properites of a single SMB share.  A
share is always part of one cluster. A share's id is a short unique string.  A
share's name is the string that is shared with clients. If a share name is not
explicitly defined the share's name is the same as the share's id.  Shares
expose part of a cephfs file system. A share must always spcecify what cephfs
volume and path to use. Optionally, the share can refer to a subvolume (and/or
subvolumegroup) by name instead of figuring out that path first. A example YAML
block looks a bit something like this:
```
resource_type: ceph.smb.share
cluster_id: clustera
share_id: pictures
name: "Staff Photo Album"
cephfs:
  volume: cephfs
  path: /pictures
  subvolumegroup: userdata
  subvolume: employees
```

As a shortcut, in both the YAML and on the command lines a subvolume `y`
belonging to a subvolumegroup `x` can be specified as `x/y` using the
`subvolume:` field or `--subvolume=` cli option.


The `ceph.smb.join.auth` resource type contains user information needed to
join an Active Directory domain. This information can be specified inside the
cluster resource or as a `ceph.smb.join.auth` to seperate the two items.
The values provided to the join auth must be a `username` and `password` for
a user with sufficient rights to join a system to an AD domain.
It is recommended to create a user on the domain with the minimal rights needed
for this purpose alone.

The `ceph.smb.usersgroups` resource defines users and groups that wil be
set up within the cluster when using a standalone (not joined to AD) cluster.
This information can be kept separate from the cluster for easier modification
and sharing the same users with multiple clusters.


Resources can be viewed with `ceph smb show`. The show subcommand can be
provided with resource type as in `ceph smb show ceph.smb.share` or resource
type plus id strings in the form `<resource_type>.<id1>[.<id2>]`.


# NOTES

* The cluster is not sent to cephadm for orchestration until at least one share
  is defined. The short version is that the cluster needs extra information
  about the volume and we don't know what volume to use until we have at least
  one share. If this proves to be too confusing or a big issue we can probably
  figure out a workaround if needed.
