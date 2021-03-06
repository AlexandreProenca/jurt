#
# Copyright (c) 2011,2012 Bogdano Arendartchuk <bogdano@mandriva.com.br>
#
# Written by Bogdano Arendartchuk <bogdano@mandriva.com.br>
#
# This file is part of Jurt Build Bot.
#
# Jurt Build Bot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2 of the License, or (at
# your option) any later version.
#
# Jurt Build Bot is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Jurt Build Bot; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
import os
import time
import logging
from jurtlib import (Error, SetupError,
        root, config, build, su,
        logger as logstore,
        packagemanager as pm)

logger = logging.getLogger("jurt.target")

UNSET_DEFAULT_TARGET = "undefined"

class PermissionError(SetupError):
    pass

class PermissionChecker:

    def __init__(self, targetconf, globalconf):
        self.targetconf = targetconf
        self.globalconf = globalconf

    def check_filesystem_permissions(self):
        import grp
        grname = self.globalconf.root.jurt_group
        logger.debug("checking if the user is a member of the %s group" %
                (grname))
        try:
            group = grp.getgrnam(grname)
        except KeyError:
            raise SetupError, ("there is no system group '%s', please check "
                    "your jurt installation (and see jurt-setup)" %
                    (grname))
        uname, uid = su.my_username()
        if uname not in group.gr_mem:
            raise PermissionError, ("your user %s should be member of the "
                    "%s group in order to jurt work. Did you run (as root) "
                    "jurt-setup -u %s ?" % (uname, grname, uname))
        if group.gr_gid not in os.getgroups():
            raise PermissionError, ("your user is NOT effectively running as a "
                    "member of the %s group, please restart your session "
                    "before running jurt" % (grname))
        sticky = [self.targetconf.roots_path, self.targetconf.spool_dir,
                self.targetconf.logs_dir, self.targetconf.failure_dir,
                self.targetconf.success_dir]
        for path in sticky:
            logger.debug("checking write permission for %s" % (path))
            if not os.access(path, os.W_OK):
                raise PermissionError, ("%s has no write permission for "
                        "you, please check your jurt installation" %
                        (path))

class Target:

    def __init__(self, name, rootmanager, packagemanager, builder,
            loggerfactory, permchecker):
        self.name = name
        self.rootmanager = rootmanager
        self.packagemanager = packagemanager
        self.builder = builder
        self.loggerfactory = loggerfactory
        self.permchecker = permchecker

    def build(self, paths, id=None, fresh=False, stage=None, timeout=None,
            outputfile=None, keeproot=False, keepbuilding=False):
        if id is None:
            id = self.builder.build_id()
        if stage:
            self.builder.set_interactive()
            self.packagemanager.check_build_stage(stage)
        logstore = self.loggerfactory.get_logger(id, outputfile)
        self.builder.build(id, fresh, paths, logstore, stage, timeout,
                keeproot, keepbuilding)

    def shell(self, id=None, fresh=False):
        if id is None:
            id = self.builder.build_id() + "-shell"
        self.builder.set_interactive()
        logstore = self.loggerfactory.get_logger(id)
        self.builder.shell(id, fresh, logstore)

    def put(self, paths, id):
        root = self.rootmanager.get_root_by_name(id, self.packagemanager,
                interactive=True)
        self.builder.set_interactive()
        username, uid = self.builder.build_user_info()
        homedir = self.builder.build_user_home(username)
        for path in paths:
            root.copy_in(path, homedir, sameuser=True)

    def pull(self, paths, id, dest, overwrite=True, dryrun=False):
        root = self.rootmanager.get_root_by_name(id, self.packagemanager,
                interactive=True)
        self.builder.set_interactive()
        username, uid = self.builder.build_user_info()
        homedir = os.path.abspath(self.builder.build_user_home(username))
        for partialglob in self.packagemanager.files_to_pull():
            globexpr = os.path.join(homedir, partialglob)
            found = root.glob(globexpr)
            for path in found:
                path = os.path.abspath(path)
                subpath = path[len(homedir)+2:]
                destpath = os.path.join(dest, subpath)
                if not overwrite and os.path.exists(destpath):
                    logger.warn("already exists, skipping: %s", destpath)
                    continue
                destdir = os.path.dirname(destpath)
                if not dryrun:
                    if not os.path.exists(destdir):
                        logger.debug("creating directories for %s", destdir)
                        os.makedirs(destdir)
                    root.copy_out([path], destpath, sameuser=True)
                yield path, destpath

    def list_roots(self):
        for rootinfo in self.rootmanager.list_roots():
            yield rootinfo

    def clean(self, dry_run=False):
        for info in self.rootmanager.clean(dry_run):
            yield info

    def keep(self, id):
        self.rootmanager.keep(id, self.packagemanager)

    def invalidate(self):
        self.rootmanager.invalidate()

    def root_path(self, id):
        return self.rootmanager.root_path(id)

    def check_permissions(self, interactive=True):
        self.permchecker.check_filesystem_permissions()
        self.rootmanager.test_sudo(interactive)

def load_target(name, globalconf, targetconf):
    loggerfactory = logstore.get_logger_factory(targetconf, globalconf)
    suwrapper = su.get_su_wrapper(name, targetconf, globalconf)
    packagemanager = pm.get_package_manager(targetconf, globalconf)
    rootmanager = root.get_root_manager(suwrapper, targetconf,
            globalconf)
    builder = build.get_builder(rootmanager, packagemanager,
            targetconf, globalconf)
    permchecker = PermissionChecker(targetconf, globalconf)
    target = Target(name, rootmanager, packagemanager, builder,
            loggerfactory, permchecker)
    return target

def get_targets_conf(globalconf):
    conf = dict(globalconf.targets())
    return conf
