#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
   Test of the omero admin control.

   Copyright 2008 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

import os
import pytest

from path import path

import omero
import omero.clients

from omero.cli import CLI, NonZeroReturnCode
from omero.plugins.admin import AdminControl
from omero.plugins.prefs import PrefsControl
from omero.util.temp_files import create_path

from mocks import MockCLI

omeroDir = path(os.getcwd()) / "build"


class TestAdmin(object):

    def setup_method(self, method):
        # Non-temp directories
        build_dir = path() / "build"
        top_dir = path() / ".." / ".." / ".."
        etc_dir = top_dir / "etc"

        # Necessary fiels
        prefs_file = build_dir / "prefs.class"
        internal_cfg = etc_dir / "internal.cfg"
        master_cfg = etc_dir / "master.cfg"

        # Temp directories
        tmp_dir = create_path(folder=True)
        tmp_etc_dir = tmp_dir / "etc"
        tmp_grid_dir = tmp_etc_dir / "grid"
        tmp_lib_dir = tmp_dir / "lib"
        tmp_var_dir = tmp_dir / "var"

        # Setup tmp dir
        [x.makedirs() for x in (tmp_grid_dir, tmp_lib_dir, tmp_var_dir)]
        prefs_file.copy(tmp_lib_dir)
        master_cfg.copy(tmp_etc_dir)
        internal_cfg.copy(tmp_etc_dir)

        # Other setup
        self.cli = MockCLI()
        self.cli.dir = tmp_dir
        self.cli.register("admin", AdminControl, "TEST")
        self.cli.register("config", PrefsControl, "TEST")

    def teardown_method(self, method):
        self.cli.teardown_method(method)

    def invoke(self, string, fails=False):
        try:
            self.cli.invoke(string, strict=True)
            if fails:
                assert False, "Failed to fail"
        except:
            if not fails:
                raise

    def testMain(self):
        try:
            self.invoke("")
        except NonZeroReturnCode:
            # Command-loop not implemented
            pass

    #
    # Async first because simpler
    #

    def XtestStartAsync(self):
        # DISABLED: https://trac.openmicroscopy.org.uk/ome/ticket/10584
        self.cli.addCall(0)
        self.cli.checksIceVersion()
        self.cli.checksStatus(1)  # I.e. not running

        self.invoke("admin startasync")
        self.cli.assertCalled()
        self.cli.assertStderr(
            ['No descriptor given. Using etc/grid/default.xml'])

    def testStopAsyncRunning(self):
        self.cli.checksStatus(0)  # I.e. running
        self.cli.addCall(0)
        self.invoke("admin stopasync")
        self.cli.assertStderr([])
        self.cli.assertStdout([])

    def testStopAsyncNotRunning(self):
        self.cli.checksStatus(1)  # I.e. not running
        self.invoke("admin stopasync", fails=True)
        self.cli.assertStderr(["Server not running"])
        self.cli.assertStdout([])

    def testStop(self):
        self.cli.checksStatus(0)  # I.e. running
        self.cli.addCall(0)
        self.cli.checksStatus(1)  # I.e. not running
        self.invoke("admin stop")
        self.cli.assertStderr([])
        self.cli.assertStdout(['Waiting on shutdown. Use CTRL-C to exit'])

    #
    # STATUS
    #

    def testStatusNodeFails(self):

        # Setup the call to bin/omero admin ice node
        popen = self.cli.createPopen()
        popen.wait().AndReturn(1)

        self.cli.mox.ReplayAll()
        pytest.raises(NonZeroReturnCode, self.invoke, "admin status")

    def testStatusSMFails(self):

        # Setup the call to bin/omero admin ice node
        popen = self.cli.createPopen()
        popen.wait().AndReturn(0)

        # Setup the call to session manager
        control = self.cli.controls["admin"]
        control._intcfg = lambda: ""

        def sm(*args):
            raise Exception("unknown")
        control.session_manager = sm

        self.cli.mox.ReplayAll()
        pytest.raises(NonZeroReturnCode, self.invoke, "admin status")

    def testStatusPasses(self):

        # Setup the call to bin/omero admin ice node
        popen = self.cli.createPopen()
        popen.wait().AndReturn(0)

        # Setup the call to session manager
        control = self.cli.controls["admin"]
        control._intcfg = lambda: ""

        def sm(*args):

            class A(object):
                def create(self, *args):
                    raise omero.WrappedCreateSessionException()
            return A()
        control.session_manager = sm

        self.cli.mox.ReplayAll()
        self.invoke("admin status")
        assert 0 == self.cli.rv


class TestAdminPorts(object):

    def setup_method(self, method):
        # # Non-temp directories
        ctxdir = path() / ".." / ".." / ".." / "dist"
        etc_dir = ctxdir / "etc"

        self.cfg_files = {}
        for f in ['internal.cfg', 'master.cfg', 'ice.config']:
            self.cfg_files[f] = etc_dir / f
        for f in ['windefault.xml', 'default.xml', 'config.xml']:
            self.cfg_files[f] = etc_dir / 'grid' / f

        # Create temp files for backup
        tmp_dir = create_path(folder=True)
        self.tmp_cfg_files = {}
        for key in self.cfg_files.keys():
            self.tmp_cfg_files[key] = tmp_dir / key

        # Create backups
        for key in self.cfg_files.keys():
            if self.cfg_files[key].exists():
                self.cfg_files[key].copy(self.tmp_cfg_files[key])
            else:
                self.tmp_cfg_files[key] = None

        # Other setup
        self.cli = CLI()
        self.cli.dir = ctxdir
        self.cli.register("admin", AdminControl, "TEST")
        self.args = ["admin", "ports"]

    def teardown_method(self, tmpdir):
        # Restore backups
        for key in self.cfg_files.keys():
            if self.tmp_cfg_files[key] is not None:
                self.tmp_cfg_files[key].copy(self.cfg_files[key])
            else:
                self.cfg_files[key].remove()

    def check_config_xml(self, prefix=None):
        config_text = self.cfg_files["config.xml"].text()
        serverport_property = (
            '<property name="omero.web.application_server.port"'
            ' value="%s4080"') % prefix
        serverlist_property = (
            '<property name="omero.web.server_list"'
            ' value="[[&quot;localhost&quot;, %s4064, &quot;omero&quot;]]"'
            ) % prefix
        if prefix:
            assert serverport_property in config_text
            assert serverlist_property in config_text
        else:
            assert serverport_property not in config_text
            assert serverlist_property not in config_text

    def check_default_xml(self, prefix=''):
        routerport = ('<variable name="ROUTERPORT"    value="%s4064"/>'
                      % prefix)
        insecure_routerport = (
            '<variable name="INSECUREROUTER" value="OMERO.Glacier2'
            '/router:tcp -p %s4063 -h @omero.host@"/>' % prefix)
        client_endpoints = ('client-endpoints="ssl -p ${ROUTERPORT}:tcp'
                            ' -p %s4063"' % prefix)
        for key in ['default.xml', 'windefault.xml']:
            s = self.cfg_files[key].text()
            assert routerport in s
            assert insecure_routerport in s
            assert client_endpoints in s

    @pytest.mark.parametrize('prefix', [1, 2])
    def testPorts(self, prefix):
        self.args += ['--prefix', '%s' % prefix]
        self.args += ['--skipcheck']
        self.cli.invoke(self.args, strict=True)

        assert self.cfg_files["ice.config"].text().endswith(
            "omero.port=%s4064\n" % prefix)
        assert "-p %s4061" % prefix in self.cfg_files["master.cfg"].text()
        assert "-p %s4061" % prefix in self.cfg_files["internal.cfg"].text()
        self.check_config_xml(prefix)
        self.check_default_xml(prefix)

        # Check revert argument
        self.args += ['--revert']
        self.cli.invoke(self.args, strict=True)
        assert not self.cfg_files["ice.config"].text().endswith(
            "omero.port=%s4064\n" % prefix)
        assert "-p 4061" in self.cfg_files["master.cfg"].text()
        assert "-p 4061" in self.cfg_files["internal.cfg"].text()
        self.check_config_xml()
        self.check_default_xml()
