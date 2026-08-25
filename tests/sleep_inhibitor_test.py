from unittest.mock import Mock, patch
from uuid import uuid4


def test_task_activity_emits_only_busy_state_transitions():
    from buzz.sleep_inhibitor import TaskActivity

    busy_changes = []
    activity = TaskActivity(busy_changes.append)
    first_task = uuid4()
    second_task = uuid4()

    activity.add(first_task)
    activity.add(second_task)
    activity.finish(first_task)
    activity.finish(second_task)

    assert busy_changes == [True, False]


def test_task_activity_clear_marks_a_busy_queue_idle():
    from buzz.sleep_inhibitor import TaskActivity

    busy_changes = []
    activity = TaskActivity(busy_changes.append)
    activity.add(uuid4())

    activity.clear()

    assert busy_changes == [True, False]


def test_task_activity_counts_requeued_task_ids_separately():
    from buzz.sleep_inhibitor import TaskActivity

    busy_changes = []
    activity = TaskActivity(busy_changes.append)
    task_id = uuid4()

    activity.add(task_id)
    activity.add(task_id)
    activity.finish(task_id)

    assert busy_changes == [True]

    activity.finish(task_id)

    assert busy_changes == [True, False]


def test_sleep_inhibitor_holds_one_assertion_for_multiple_tasks():
    from buzz.sleep_inhibitor import SleepInhibitor

    backend = Mock()
    inhibitor = SleepInhibitor(backend=backend, enabled=True)

    inhibitor.set_busy(True)
    inhibitor.set_busy(True)
    assert inhibitor.active

    inhibitor.set_busy(False)

    assert not inhibitor.active
    backend.acquire.assert_called_once_with()
    backend.release.assert_called_once_with()


def test_sleep_inhibitor_reacts_to_setting_changes_while_busy():
    from buzz.sleep_inhibitor import SleepInhibitor

    backend = Mock()
    inhibitor = SleepInhibitor(backend=backend, enabled=False)
    inhibitor.set_busy(True)
    assert not inhibitor.active

    inhibitor.set_enabled(True)
    assert inhibitor.active

    inhibitor.set_enabled(False)
    assert not inhibitor.active
    backend.acquire.assert_called_once_with()
    backend.release.assert_called_once_with()


def test_windows_backend_sets_and_clears_system_required_flag():
    from buzz.sleep_inhibitor import (
        ES_CONTINUOUS,
        ES_SYSTEM_REQUIRED,
        WindowsSleepBackend,
    )

    set_execution_state = Mock(return_value=1)
    backend = WindowsSleepBackend(set_execution_state=set_execution_state)

    backend.acquire()
    backend.release()

    assert set_execution_state.call_args_list == [
        ((ES_CONTINUOUS | ES_SYSTEM_REQUIRED,),),
        ((ES_CONTINUOUS,),),
    ]


def test_macos_backend_owns_caffeinate_process():
    from buzz.sleep_inhibitor import MacOSSleepBackend

    process = Mock()
    popen = Mock(return_value=process)
    backend = MacOSSleepBackend(popen=popen)

    with patch("buzz.sleep_inhibitor.os.getpid", return_value=1234):
        backend.acquire()
    backend.release()

    popen.assert_called_once_with(
        ["caffeinate", "-i", "-w", "1234"],
        stdout=-3,
        stderr=-3,
    )
    process.terminate.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=5)
