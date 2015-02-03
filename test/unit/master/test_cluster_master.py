from unittest.mock import MagicMock, Mock
from genty import genty, genty_dataset
import time

from app.master.atomizer import Atomizer
from app.master.build import Build
from app.master.build_request import BuildRequest
from app.master.cluster_master import ClusterMaster
from app.master.job_config import JobConfig
from app.master.slave import Slave
from app.slave.cluster_slave import SlaveState
from app.util.exceptions import BadRequestError, ItemNotFoundError
from test.framework.base_unit_test_case import BaseUnitTestCase


@genty
class TestClusterMaster(BaseUnitTestCase):

    def setUp(self):
        super().setUp()
        self.patch('app.util.fs.create_dir')
        self.patch('app.util.fs.async_delete')

    def test_updating_slave_to_idle_state_marks_build_finished_when_slaves_are_done(self):
        master = ClusterMaster()
        slave1 = Slave('', 1)
        slave2 = Slave('', 1)
        slave3 = Slave('', 1)
        slave1.current_build_id = 1
        slave2.current_build_id = None
        slave3.current_build_id = 3
        build1 = Build(BuildRequest({}))
        master._all_slaves_by_url = {'1': slave1, '2': slave2, '3': slave3}
        master._all_builds_by_id = {1: build1}
        build1._build_id = 1
        build1.finish = MagicMock()
        master.handle_slave_state_update(slave1, SlaveState.IDLE)
        build1.finish.assert_called_once_with()

    def test_updating_slave_to_idle_state_does_not_mark_build_finished_when_slaves_not_done(self):
        master = ClusterMaster()
        slave1 = Slave('', 1)
        slave2 = Slave('', 1)
        slave3 = Slave('', 1)
        slave1.current_build_id = 1
        slave2.current_build_id = None
        slave3.current_build_id = 1
        build1 = Build(BuildRequest({}))
        master._all_slaves_by_url = {'1': slave1, '2': slave2, '3': slave3}
        master._all_builds_by_id = {1: build1}
        build1._build_id = 1
        build1.finish = MagicMock()
        master.handle_slave_state_update(slave1, SlaveState.IDLE)
        self.assertFalse(build1.finish.called)

    @genty_dataset(
        slave_id_specified=({'slave_id': 400},),
        slave_url_specified=({'slave_url': 'michelangelo.turtles.gov'},),
    )
    def test_get_slave_raises_exception_on_slave_not_found(self, get_slave_kwargs):
        master = ClusterMaster()
        master.connect_new_slave('raphael.turtles.gov', 10)
        master.connect_new_slave('leonardo.turtles.gov', 10)
        master.connect_new_slave('donatello.turtles.gov', 10)

        with self.assertRaises(ItemNotFoundError):
            master.get_slave(**get_slave_kwargs)

    @genty_dataset(
        both_arguments_specified=({'slave_id': 1, 'slave_url': 'raphael.turtles.gov'},),
        neither_argument_specified=({},),
    )
    def test_get_slave_raises_exception_on_invalid_arguments(self, get_slave_kwargs):
        master = ClusterMaster()
        master.connect_new_slave('raphael.turtles.gov', 10)

        with self.assertRaises(ValueError):
            master.get_slave(**get_slave_kwargs)

    def test_get_slave_returns_expected_value_given_valid_arguments(self):
        master = ClusterMaster()
        master.connect_new_slave('raphael.turtles.gov', 10)
        master.connect_new_slave('leonardo.turtles.gov', 10)
        master.connect_new_slave('donatello.turtles.gov', 10)

        actual_slave_by_id = master.get_slave(slave_id=2)
        actual_slave_by_url = master.get_slave(slave_url='leonardo.turtles.gov')

        self.assertEqual(2, actual_slave_by_id.id, 'Retrieved slave should have the same id as requested.')
        self.assertEqual('leonardo.turtles.gov', actual_slave_by_url.url,
                         'Retrieved slave should have the same url as requested.')

    def test_update_build_with_valid_params_succeeds(self):
        build_id = 1
        update_params = {'key': 'value'}
        master = ClusterMaster()
        build = Mock()
        master._all_builds_by_id[build_id] = build
        build.validate_update_params = Mock(return_value=(True, update_params))
        build.update_state = Mock()

        success, response = master.handle_request_to_update_build(build_id, update_params)

        build.update_state.assert_called_once_with(update_params)
        self.assertTrue(success, "Update build should return success")
        self.assertEqual(response, {}, "Response should be empty")

    def test_update_build_with_bad_build_id_fails(self):
        build_id = 1
        invalid_build_id = 2
        update_params = {'key': 'value'}
        master = ClusterMaster()
        build = Mock()
        master._all_builds_by_id[build_id] = build
        build.validate_update_params = Mock(return_value=(True, update_params))
        build.update_state = Mock()

        self.assertRaises(ItemNotFoundError, master.handle_request_to_update_build, invalid_build_id, update_params)

    def test_updating_slave_to_disconnected_state_should_mark_slave_as_dead(self):
        master = ClusterMaster()
        slave_url = 'raphael.turtles.gov'
        master.connect_new_slave(slave_url, 10)
        slave = master.get_slave(slave_url=slave_url)
        self.assertTrue(slave.is_alive())

        master.handle_slave_state_update(slave, SlaveState.DISCONNECTED)

        self.assertFalse(slave.is_alive())

    def test_updating_slave_to_setup_completed_state_should_tell_build_to_begin_subjob_execution(self):
        master = ClusterMaster()
        fake_build = MagicMock()
        master.get_build = MagicMock(return_value=fake_build)
        slave_url = 'raphael.turtles.gov'
        master.connect_new_slave(slave_url, 10)
        slave = master.get_slave(slave_url=slave_url)

        master.handle_slave_state_update(slave, SlaveState.SETUP_COMPLETED)

        fake_build.begin_subjob_executions_on_slave.assert_called_once_with(slave)

    def test_updating_slave_to_nonexistent_state_should_raise_bad_request_error(self):
        master = ClusterMaster()
        slave_url = 'raphael.turtles.gov'
        master.connect_new_slave(slave_url, 10)
        slave = master.get_slave(slave_url=slave_url)

        with self.assertRaises(BadRequestError):
            master.handle_slave_state_update(slave, 'NONEXISTENT_STATE')

    def test_handle_result_reported_from_slave_does_nothing_when_build_is_canceled(self):
        build_id = 1
        slave_url = "url"
        build = Build(BuildRequest({}))
        build.handle_subjob_payload = Mock()
        build.mark_subjob_complete = Mock()
        build.execute_next_subjob_on_slave = Mock()
        master = ClusterMaster()
        master._all_builds_by_id[build_id] = build
        master._all_slaves_by_url[slave_url] = Mock()
        build._is_canceled = True

        master.handle_result_reported_from_slave(slave_url, build_id, 1)

        self.assertEqual(build.handle_subjob_payload.call_count, 0, "Build is canceled, should not handle payload")
        self.assertEqual(build.mark_subjob_complete.call_count, 0, "Build is canceled, should not complete subjobs")
        self.assertEqual(build.execute_next_subjob_on_slave.call_count, 0,
                         "Build is canceled, should not do next subjob")

    def test_handle_build(self):
        master = ClusterMaster()
        build = Build(BuildRequest({'type': 'directory', 'project_directory': '/tmp/asdf'}))
        build.generate_project_type()
        build.project_type.fetch_project = Mock()
        build.project_type.job_config = Mock(return_value=JobConfig('name', None, None, '', Atomizer([]), 10, 10))
        build.needs_more_slaves = Mock(return_value=False)
        master._queue_build(build)

        while build.needs_more_slaves.call_count == 0:
            time.sleep(1)
        self.assertEqual(build.needs_more_slaves.call_count, 1)

