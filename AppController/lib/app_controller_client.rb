#!/usr/bin/ruby -w

require 'openssl'
require 'soap/rpc/driver'
require 'timeout'

require 'custom_exceptions'
require 'helperfunctions'

IP_REGEX = /\d+\.\d+\.\d+\.\d+/

FQDN_REGEX = /[\w\d\.\-]+/

IP_OR_FQDN = /#{IP_REGEX}|#{FQDN_REGEX}/

# Sometimes SOAP calls take a long time if large amounts of data are being
# sent over the network: for this first version we don't want these calls to
# endlessly timeout and retry, so as a hack, just don't let them timeout.
# The next version should replace this and properly timeout and not use
# long calls unless necessary.
NO_TIMEOUT = 100000

RETRY_ON_FAIL = true

ABORT_ON_FAIL = false

# A client that uses SOAP messages to communicate with the underlying cloud
# platform (here, AppScale). This client is similar to that used in the AppScale
# Tools, but with non-Neptune SOAP calls removed.
class AppControllerClient
  # The SOAP client that we use to communicate with the AppController.
  attr_accessor :conn

  # The IP address of the AppController that we will be connecting to.
  attr_accessor :ip

  # The secret string that is used to authenticate this client with
  # AppControllers. It is initially generated by appscale-run-instances and can
  # be found on the machine that ran that tool, or on any AppScale machine.
  attr_accessor :secret

  # The port that the AppController binds to, by default.
  SERVER_PORT = 17443

  # A constructor that requires both the IP address of the machine to
  # communicate with as well as the secret (string) needed to perform
  # communication.  AppControllers will reject SOAP calls if this secret
  # (basically a password) is not present - it can be found in the
  # /etc/appscale directory, and a helper method is usually present to
  # fetch this for us.
  def initialize(ip, secret)
    @ip = ip
    @secret = secret

    @conn = SOAP::RPC::Driver.new("https://#{@ip}:#{SERVER_PORT}")
    # Disable certificate verification.
    @conn.options['protocol.http.ssl_config.verify_mode'] = nil
    @conn.add_method('set_parameters', 'layout', 'options', 'secret')
    @conn.add_method('upload_app', 'archived_file', 'file_suffix', 'secret')
    @conn.add_method('get_all_public_ips', 'secret')
    @conn.add_method('is_done_initializing', 'secret')
    @conn.add_method('get_property', 'property_regex', 'secret')
    @conn.add_method('set_property', 'property_name', 'property_value', 'secret')
    @conn.add_method('set_node_read_only', 'read_only', 'secret')
    @conn.add_method('primary_db_is_up', 'secret')
    @conn.add_method('get_app_upload_status', 'reservation_id', 'secret')
    @conn.add_method('get_cluster_stats_json', 'secret')
    @conn.add_method('get_node_stats_json', 'secret')
    @conn.add_method('get_instance_info', 'secret')
    @conn.add_method('get_request_info', 'version_key', 'secret')
    @conn.add_method('update_cron', 'project_id', 'secret')
  end

  # Provides automatic retry logic for transient SOAP errors. This code is
  # used in few other clients (it should be made in a library):
  #   lib/infrastructure_manager_client.rb
  #   lib/user_app_client.rb
  #   lib/app_controller_client.rb
  # Modification in this function should be reflected on the others too.
  #
  # Args:
  #   time: A Integer that indicates how long the timeout should be set to when
  #     executing the caller's block.
  #   retry_on_except: A boolean that indicates if non-transient Exceptions
  #     should result in the caller's block being retried or not.
  #   callr: A String that names the caller's method, used for debugging
  #     purposes.
  #
  # Raises:
  #   FailedNodeException: if the given block contacted a machine that
  #     is either not running or is rejecting connections.
  #   SystemExit: If a non-transient Exception was thrown when executing the
  #     given block.
  # Returns:
  #   The result of the block that was executed, or nil if the timeout was
  #   exceeded.
  def make_call(time, retry_on_except, callr)
    begin
      Timeout.timeout(time) {
        begin
          if block_given?
            ret = yield
            msg = ''
            if ret == BAD_SECRET_MSG
              msg = "Bad secret talking with #{@ip}."
            elsif ret == INVALID_REQUEST
              msg = "Got INVALID_REQUEST from #{@ip}."
            end
            unless msg.empty?
              Djinn.log_warn(msg)
              raise FailedNodeException.new(msg)
            end
            return ret
          end
        rescue Errno::ECONNREFUSED, Errno::EHOSTUNREACH,
          OpenSSL::SSL::SSLError, NotImplementedError, Errno::EPIPE,
          Errno::ECONNRESET, SOAP::EmptyResponseError, StandardError => e
          if retry_on_except
            Kernel.sleep(1)
            Djinn.log_debug("[#{callr}] exception in make_call to " \
              "#{@ip}:#{SERVER_PORT}. Exception class: #{e.class}. Retrying...")
            retry
          else
            trace = e.backtrace.join("\n")
            Djinn.log_warn('Exception encountered while talking to ' \
              "#{@ip}:#{SERVER_PORT}.\n#{trace}")
            raise FailedNodeException.new("Exception #{e.class}:#{e.message} encountered " \
              "while talking to #{@ip}:#{SERVER_PORT}.")
          end
        end
      }
    rescue Timeout::Error
      Djinn.log_warn("[#{callr}] SOAP call to #{@ip} timed out")
      raise FailedNodeException.new("Time out talking to #{@ip}:#{SERVER_PORT}")
    end
  end

  def set_parameters(layout, options)
    result = ""
    make_call(10, ABORT_ON_FAIL, 'set_parameters') {
      result = conn.set_parameters(layout, options, @secret)
    }
    if result =~ /Error:/
      raise FailedNodeException.new("set_parameters returned #{result}.")
    end
  end

  def upload_app(archived_file, file_suffix)
    make_call(30, RETRY_ON_FAIL, 'upload_app') {
      @conn.upload_app(archived_file, file_suffix, @secret)
    }
  end

  def is_done_initializing?
    make_call(30, RETRY_ON_FAIL, 'is_done_initializing') { @conn.is_done_initializing(@secret) }
  end

  def get_all_public_ips
    make_call(30, RETRY_ON_FAIL, 'get_all_public_ips') { @conn.get_all_public_ips(@secret) }
  end

  def get_property(property_regex)
    make_call(NO_TIMEOUT, RETRY_ON_FAIL, 'get_property') {
      @conn.get_property(property_regex, @secret)
    }
  end

  def set_property(property_name, property_value)
    make_call(NO_TIMEOUT, RETRY_ON_FAIL, 'set_property') {
      @conn.set_property(property_name, property_value, @secret)
    }
  end

  # Enables or disables datastore writes on the remote database node.
  def set_node_read_only(read_only)
    make_call(NO_TIMEOUT, RETRY_ON_FAIL, 'set_node_read_only') {
      @conn.set_node_read_only(read_only, @secret)
    }
  end

  # Checks if the Cassandra seed node is up.
  def primary_db_is_up
    make_call(NO_TIMEOUT, RETRY_ON_FAIL, 'primary_db_is_up') {
      @conn.primary_db_is_up(@secret)
    }
  end

  # Checks the status of an app upload.
  def get_app_upload_status(reservation_id)
    make_call(NO_TIMEOUT, RETRY_ON_FAIL, 'get_app_upload_status') {
      @conn.get_app_upload_status(reservation_id, @secret)
    }
  end

  # Gets the statistics of all the nodes in the AppScale deployment.
  def get_cluster_stats_json
    make_call(10, RETRY_ON_FAIL, 'get_cluster_stats_json') {
      @conn.get_cluster_stats_json(@secret)
    }
  end

  # Gets the statistics of this node
  def get_node_stats_json
    make_call(10, RETRY_ON_FAIL, 'get_node_stats_json') {
      @conn.get_node_stats_json(@secret)
    }
  end

  # Gets the statistics of this node
  def update_cron(project_id)
    make_call(10, RETRY_ON_FAIL, 'update_cron') {
      @conn.update_cron(project_id, @secret)
    }
  end

end
