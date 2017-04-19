import StringIO
import csv
import logging
import subprocess
import time
from collections import defaultdict
from datetime import datetime

import attr


class _UnknownValue(object):
  """
  Instance of this private class denotes unknown value.
  It's used to denote values of stats properties which are missed
  in haproxy stats csv
  """

  def __nonzero__(self):
    return False

  def __repr__(self):
    return "-"


UNKNOWN_VALUE = _UnknownValue()


@attr.s(cmp=False, hash=False, slots=True, frozen=True)
class HAProxyListenerStats(object):
  """
  For more details see
  https://cbonte.github.io/haproxy-dconv/1.5/configuration.html#9.1
  """
  pxname = attr.ib()  # proxy name
  svname = attr.ib()  # service name (FRONTEND, BACKEND or name of server/listener)
  scur = attr.ib()  # current sessions
  smax = attr.ib()  # max sessions
  slim = attr.ib()  # configured session limit
  stot = attr.ib()  # cumulative num of connections
  bin = attr.ib()  # bytes in
  bout = attr.ib()  # bytes out
  dreq = attr.ib()  # reqs denied because of security concerns
  dresp = attr.ib()  # resps denied because of security concerns
  ereq = attr.ib()  # request errors
  status = attr.ib()  # status (UP/DOWN/NOLB/MAINT/MAINT(via)...)
  pid = attr.ib()  # process id (0 for first instance, 1 for second, ...)
  iid = attr.ib()  # unique proxy id
  sid = attr.ib()  # server id (unique inside a proxy)
  type = attr.ib()  # (0=frontend, 1=backend, 2=server, 3=socket/listener)


@attr.s(cmp=False, hash=False, slots=True, frozen=True)
class HAProxyFrontendStats(object):
  """
  For more details see
  https://cbonte.github.io/haproxy-dconv/1.5/configuration.html#9.1
  """
  pxname = attr.ib()  # proxy name
  svname = attr.ib()  # service name (FRONTEND, BACKEND or name of server/listener)
  scur = attr.ib()  # current sessions
  smax = attr.ib()  # max sessions
  slim = attr.ib()  # configured session limit
  stot = attr.ib()  # cumulative num of connections
  bin = attr.ib()  # bytes in
  bout = attr.ib()  # bytes out
  dreq = attr.ib()  # reqs denied because of security concerns
  dresp = attr.ib()  # resps denied because of security concerns
  ereq = attr.ib()  # request errors
  status = attr.ib()  # status (UP/DOWN/NOLB/MAINT/MAINT(via)...)
  pid = attr.ib()  # process id (0 for first instance, 1 for second, ...)
  iid = attr.ib()  # unique proxy id
  type = attr.ib()  # (0=frontend, 1=backend, 2=server, 3=socket/listener)
  rate = attr.ib()  # num of sessions per second over last elapsed second
  rate_lim = attr.ib()  # configured limit on new sessions per second
  rate_max = attr.ib()  # max num of new sessions per second
  hrsp_1xx = attr.ib()  # http resps with 1xx code
  hrsp_2xx = attr.ib()  # http resps with 2xx code
  hrsp_3xx = attr.ib()  # http resps with 3xx code
  hrsp_4xx = attr.ib()  # http resps with 4xx code
  hrsp_5xx = attr.ib()  # http resps with 5xx code
  hrsp_other = attr.ib()  # http resps with other codes (protocol error)
  req_rate = attr.ib()  # HTTP reqs per second over last elapsed second
  req_rate_max = attr.ib()  # max num of HTTP reqs per second observed
  req_tot = attr.ib()  # total num of HTTP reqs received
  comp_in = attr.ib()  # num of HTTP resp bytes fed to the compressor
  comp_out = attr.ib()  # num of HTTP resp bytes emitted by the compressor
  comp_byp = attr.ib()  # num of bytes that bypassed the HTTP compressor
  comp_rsp = attr.ib()  # num of HTTP resps that were compressed


@attr.s(cmp=False, hash=False, slots=True, frozen=True)
class HAProxyBackendStats(object):
  """
  For more details see
  https://cbonte.github.io/haproxy-dconv/1.5/configuration.html#9.1
  """
  pxname = attr.ib()  # proxy name
  svname = attr.ib()  # service name (FRONTEND, BACKEND or name of server/listener)
  qcur = attr.ib()  # current queued reqs. For the backend this reports the
  qmax = attr.ib()  # max value of qcur
  scur = attr.ib()  # current sessions
  smax = attr.ib()  # max sessions
  slim = attr.ib()  # configured session limit
  stot = attr.ib()  # cumulative num of connections
  bin = attr.ib()  # bytes in
  bout = attr.ib()  # bytes out
  dreq = attr.ib()  # reqs denied because of security concerns
  dresp = attr.ib()  # resps denied because of security concerns
  econ = attr.ib()  # num of reqs that encountered an error
  eresp = attr.ib()  # resp errors. srv_abrt will be counted here also
  wretr = attr.ib()  # num of times a connection to a server was retried
  wredis = attr.ib()  # num of times a request was redispatched
  status = attr.ib()  # status (UP/DOWN/NOLB/MAINT/MAINT(via)...)
  weight = attr.ib()  # total weight
  act = attr.ib()  # num of active servers
  bck = attr.ib()  # num of backup servers
  chkdown = attr.ib()  # num of UP->DOWN transitions. The backend counter counts
  lastchg = attr.ib()  # num of seconds since the last UP<->DOWN transition
  downtime = attr.ib()  # total downtime (in seconds). The value for the backend
  pid = attr.ib()  # process id (0 for first instance, 1 for second, ...)
  iid = attr.ib()  # unique proxy id
  lbtot = attr.ib()  # total num of times a server was selected, either for new
  type = attr.ib()  # (0=frontend, 1=backend, 2=server, 3=socket/listener)
  rate = attr.ib()  # num of sessions per second over last elapsed second
  rate_max = attr.ib()  # max num of new sessions per second
  hrsp_1xx = attr.ib()  # http resps with 1xx code
  hrsp_2xx = attr.ib()  # http resps with 2xx code
  hrsp_3xx = attr.ib()  # http resps with 3xx code
  hrsp_4xx = attr.ib()  # http resps with 4xx code
  hrsp_5xx = attr.ib()  # http resps with 5xx code
  hrsp_other = attr.ib()  # http resps with other codes (protocol error)
  cli_abrt = attr.ib()  # num of data transfers aborted by the client
  srv_abrt = attr.ib()  # num of data transfers aborted by the server
  comp_in = attr.ib()  # num of HTTP resp bytes fed to the compressor
  comp_out = attr.ib()  # num of HTTP resp bytes emitted by the compressor
  comp_byp = attr.ib()  # num of bytes that bypassed the HTTP compressor
  comp_rsp = attr.ib()  # num of HTTP resps that were compressed
  lastsess = attr.ib()  # num of seconds since last session assigned to
  qtime = attr.ib()  # the avg queue time in ms over the 1024 last reqs
  ctime = attr.ib()  # the avg connect time in ms over the 1024 last reqs
  rtime = attr.ib()  # the avg resp time in ms over the 1024 last reqs
  ttime = attr.ib()  # the avg total session time in ms over the 1024 last


@attr.s(cmp=False, hash=False, slots=True, frozen=True)
class HAProxyServerStats(object):
  """
  For more details see
  https://cbonte.github.io/haproxy-dconv/1.5/configuration.html#9.1
  """
  unified_server_name = attr.ib()  # reference for linking with process stats
  pxname = attr.ib()  # proxy name
  svname = attr.ib()  # service name (FRONTEND, BACKEND or name of server/listener)
  qcur = attr.ib()  # current queued reqs. For the backend this reports the
  qmax = attr.ib()  # max value of qcur
  scur = attr.ib()  # current sessions
  smax = attr.ib()  # max sessions
  slim = attr.ib()  # configured session limit
  stot = attr.ib()  # cumulative num of connections
  bin = attr.ib()  # bytes in
  bout = attr.ib()  # bytes out
  dresp = attr.ib()  # resps denied because of security concerns.
  econ = attr.ib()  # num of reqs that encountered an error trying to
  eresp = attr.ib()  # resp errors. srv_abrt will be counted here also.
  wretr = attr.ib()  # num of times a connection to a server was retried.
  wredis = attr.ib()  # num of times a request was redispatched to another
  status = attr.ib()  # status (UP/DOWN/NOLB/MAINT/MAINT(via)...)
  weight = attr.ib()  # server weight
  act = attr.ib()  # server is active
  bck = attr.ib()  # server is backup
  chkfail = attr.ib()  # num of failed checks
  chkdown = attr.ib()  # num of UP->DOWN transitions
  lastchg = attr.ib()  # num of seconds since the last UP<->DOWN transition
  downtime = attr.ib()  # total downtime (in seconds)
  qlimit = attr.ib()  # configured maxqueue for the server
  pid = attr.ib()  # process id (0 for first instance, 1 for second, ...)
  iid = attr.ib()  # unique proxy id
  sid = attr.ib()  # server id (unique inside a proxy)
  throttle = attr.ib()  # current throttle percentage for the server
  lbtot = attr.ib()  # total num of times a server was selected
  tracked = attr.ib()  # id of proxy/server if tracking is enabled.
  type = attr.ib()  # (0=frontend, 1=backend, 2=server, 3=socket/listener)
  rate = attr.ib()  # num of sessions per second over last elapsed second
  rate_max = attr.ib()  # max num of new sessions per second
  check_status = attr.ib()  # status of last health check
  check_code = attr.ib()  # layer5-7 code, if available
  check_duration = attr.ib()  # time in ms took to finish last health check
  hrsp_1xx = attr.ib()  # http resps with 1xx code
  hrsp_2xx = attr.ib()  # http resps with 2xx code
  hrsp_3xx = attr.ib()  # http resps with 3xx code
  hrsp_4xx = attr.ib()  # http resps with 4xx code
  hrsp_5xx = attr.ib()  # http resps with 5xx code
  hrsp_other = attr.ib()  # http resps with other codes (protocol error)
  hanafail = attr.ib()  # failed health checks details
  cli_abrt = attr.ib()  # num of data transfers aborted by the client
  srv_abrt = attr.ib()  # num of data transfers aborted by the server
  lastsess = attr.ib()  # num of seconds since last session assigned to
  last_chk = attr.ib()  # last health check contents or textual error
  last_agt = attr.ib()  # last agent check contents or textual error
  qtime = attr.ib()  # the avg queue time in ms over the 1024 last reqs
  ctime = attr.ib()  # the avg connect time in ms over the 1024 last reqs
  rtime = attr.ib()  # the avg resp time in ms over the 1024 last reqs
  ttime = attr.ib()  # the avg total session time in ms over the 1024 last


ALL_HAPROXY_FIELDS = set(
  HAProxyListenerStats.__slots__ + HAProxyFrontendStats.__slots__
  + HAProxyBackendStats.__slots__ + HAProxyServerStats.__slots__
)
KNOWN_NON_INTEGER_FIELDS = {
  'pxname', 'svname', 'status', 'check_status', 'last_chk', 'last_agt'
}
INTEGER_FIELDS = set(ALL_HAPROXY_FIELDS) - KNOWN_NON_INTEGER_FIELDS


class InvalidHAProxyStats(ValueError):
  pass


@attr.s(cmp=False, hash=False, slots=True, frozen=True)
class ProxyStats(object):
  """
  Object of ProxyStats is kind of structured container for all haproxy stats
  provided for the specific proxy (e.g.: TaskQueue, UserAppServer, ...)

  Only those Hermes nodes which are collocated with HAProxy collects this stats.
  """
  name = attr.ib()
  unified_service_name = attr.ib()
  utc_timestamp = attr.ib()
  frontend = attr.ib()  # HAProxyFrontendStats
  backend = attr.ib()  # HAProxyBackendStats
  servers = attr.ib()  # list[HAProxyServerStats]
  listeners = attr.ib()  # list[HAProxyListenerStats]

  @staticmethod
  def _get_field_value(row, field_name):
    """ Private method for getting value from csv cell """
    if field_name not in row:
      return UNKNOWN_VALUE
    value = row[field_name]
    if not value:
      return None
    if field_name in INTEGER_FIELDS:
      return int(value)
    return value

  @staticmethod
  def current_proxies(stats_socket_path, names_mapper):
    """ Static method which parses haproxy stats and returns detailed
    proxy statistics for all proxies.

    Args:
      stats_socket_path: a str representing path to haproxy stats socket
      names_mapper: an object with method 'from_haproxy_name' which
                             returns a tuple
                             (<appscale-service-group>, <appscale-service-name>) 
    Returns:
      list[ProxyStats]
    """
    # Get CSV table with haproxy stats
    csv_text = subprocess.check_output(
      "echo 'show stat' | socat stdio unix-connect:{}"
        .format(stats_socket_path), shell=True
    ).replace("# ", "", 1)
    csv_buffer = StringIO.StringIO(csv_text)
    table = csv.DictReader(csv_buffer, delimiter=',')
    missed_fields = ALL_HAPROXY_FIELDS - set(table.fieldnames)
    if missed_fields:
      logging.warning("HAProxy stats fields {} are missed. Old version of "
                      "HAProxy is probably used (v1.5+ is expected)"
                      .format(list(missed_fields)))

    utc_timestamp = time.mktime(datetime.utcnow().timetuple())

    # Parse haproxy stats output line by line
    parsed_objects = defaultdict(list)
    for row in table:
      proxy_name = row['pxname']
      svname = row['svname']
      if svname == 'FRONTEND':
        stats_type = HAProxyFrontendStats
      elif svname == 'BACKEND':
        stats_type = HAProxyBackendStats
      elif row['qcur']:
        # Listener stats doesn't have "current queued requests" property
        stats_type = HAProxyServerStats
      else:
        stats_type = HAProxyListenerStats

      stats_values = {
        field: ProxyStats._get_field_value(row, field)
        for field in stats_type.__slots__
      }

      server_name = names_mapper.get_server_name(proxy_name, svname)
      stats = stats_type(unified_server_name=server_name, **stats_values)
      parsed_objects[proxy_name].append(stats)

    # Attempt to merge separate stats object to ProxyStats instances
    proxy_stats_list = []
    for proxy_name, stats_objects in parsed_objects.iteritems():
      frontends = [stats for stats in stats_objects
                   if isinstance(stats, HAProxyFrontendStats)]
      backends = [stats for stats in stats_objects
                  if isinstance(stats, HAProxyBackendStats)]
      servers = [stats for stats in stats_objects
                 if isinstance(stats, HAProxyServerStats)]
      listeners = [stats for stats in stats_objects
                   if isinstance(stats, HAProxyListenerStats)]
      if len(frontends) != 1 or len(backends) != 1:
        raise InvalidHAProxyStats(
          "Exactly one FRONTEND and one BACKEND line should correspond to "
          "a single proxy. Proxy '{}' has {} frontends and {} backends"
            .format(proxy_name, len(frontends), len(backends))
        )

      # Create ProxyStats object which contains all stats related to the proxy
      service_name = names_mapper.get_service_name(proxy_name)
      proxy_stats = ProxyStats(
        name=proxy_name, unified_service_name=service_name,
        utc_timestamp=utc_timestamp, frontend=frontends[0], backend=backends[0],
        servers=servers, listeners=listeners
      )
      proxy_stats_list.append(proxy_stats)

    return proxy_stats_list

  @staticmethod
  def fromdict(dictionary):
    """ Addition to attr.asdict function.
    Args:
      dictionary: a dict with all fields required to build ProxyStats obj. 
    Returns:
      an instance of ProxyStats
    """
    pass