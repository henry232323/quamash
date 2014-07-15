import asyncio
import os.path
import logging
import sys
import locale
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

try:
	from PyQt5.QtWidgets import QApplication
except ImportError:
	from PySide.QtGui import QApplication
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import quamash


logging.basicConfig(
	level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')


class _SubprocessProtocol(asyncio.SubprocessProtocol):
	def __init__(self, *args, **kwds):
		super(_SubprocessProtocol, self).__init__(*args, **kwds)
		self.received_stdout = None

	def pipe_data_received(self, fd, data):
		text = data.decode(locale.getpreferredencoding(False))
		if fd == 1:
			self.received_stdout = text.strip()

	def process_exited(self):
		asyncio.get_event_loop().stop()


@pytest.fixture(scope='session')
def application():
	app = QApplication([])
	return app


@pytest.fixture
def loop(request, application):
	lp = quamash.QEventLoop(application)
	asyncio.set_event_loop(lp)

	def fin():
		try:
			lp.close()
		finally:
			asyncio.set_event_loop(None)

	request.addfinalizer(fin)
	return lp


@pytest.fixture(
	params=[None, quamash.QThreadExecutor, ThreadPoolExecutor, ProcessPoolExecutor],
)
def executor(request):
	exc_cls = request.param
	if exc_cls is None:
		return None

	exc = exc_cls(5)  # FIXME? fixed number of workers
	request.addfinalizer(exc.shutdown)
	return exc


def test_can_run_tasks_in_executor(loop, executor):
	"""Verify that tasks can be run in default (threaded) executor."""
	def blocking_func():
		nonlocal was_invoked
		was_invoked = True

	was_invoked = False
	loop.run_until_complete(loop.run_in_executor(None, blocking_func))

	assert was_invoked


def test_can_handle_exception_in_default_executor(loop):
	"""Verify that exceptions from tasks run in default (threaded) executor are handled."""
	def blocking_func():
		raise Exception('Testing')

	with pytest.raises(Exception) as excinfo:
		loop.run_until_complete(loop.run_in_executor(None, blocking_func))

	assert str(excinfo.value) == 'Testing'


def test_can_execute_subprocess(loop):
	"""Verify that a subprocess can be executed."""
	transport, protocol = loop.run_until_complete(loop.subprocess_exec(
		_SubprocessProtocol, sys.executable or 'python', '-c', 'print(\'Hello async world!\')'))
	loop.run_forever()
	assert transport.get_returncode() == 0
	assert protocol.received_stdout == 'Hello async world!'


def test_can_terminate_subprocess(loop):
	"""Verify that a subprocess can be terminated."""
	# Start a never-ending process
	transport = loop.run_until_complete(
		loop.subprocess_exec(
			_SubprocessProtocol, sys.executable or 'python', '-c', 'import time\nwhile True: time.sleep(1)',
		),
	)[0]
	# Terminate!
	transport.kill()
	# Wait for process to die
	loop.run_forever()

	assert transport.get_returncode() != 0


def test_can_function_as_context_manager(application):
	"""Verify that a QEventLoop can function as its own context manager."""
	with quamash.QEventLoop(application) as loop:
		assert isinstance(loop, quamash.QEventLoop)
		loop.call_soon(loop.stop)
		loop.run_forever()
