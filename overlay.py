import abc
import logging

from keyvault.crypto import ECCrypto
from messaging.interfaces.endpoint import EndpointListener
from messaging.serialization import Serializer
from peer import Peer
from taskmanager import TaskManager


class Overlay(EndpointListener, TaskManager):
    """
    Interface for an Internet overlay.
    """

    __metaclass__ = abc.ABCMeta

    def __init__(self, master_peer, my_peer, endpoint, database):
        """
        Create a new overlay for the Internet.

        :param master_peer: the (public key) peer of the owner of this overlay.
        :param my_peer: the (private key) peer of this peer
        :param endpoint: the endpoint to use for messaging
        :param database: the database to use for storage
        """
        EndpointListener.__init__(self, True)
        TaskManager.__init__(self)
        self.serializer = self.get_serializer()
        self.crypto = ECCrypto()

        self.master_peer = master_peer
        self.my_peer = my_peer

        self.endpoint = endpoint
        self.endpoint.add_listener(self)

        self.logger = logging.getLogger(self.__class__.__name__)

        self.database = database

    def unload(self):
        """
        Called when this overlay needs to shut down.
        """
        self.cancel_all_pending_tasks()

    def get_serializer(self):
        """
        Get a Serializer for this Overlay.
        """
        return Serializer()

    def on_packet(self, packet):
        """
        Callback for when data is received on this endpoint.

        :param packet: the received packet, in (source, binary string) format.
        """
        source_address, data = packet
        key_bin, data = self.split_key_data(data)
        key = self.crypto.key_from_public_bin(key_bin)
        self.on_data(Peer(key, source_address), data)

    @abc.abstractmethod
    def split_key_data(self, data):
        """
        Split a data string into a key string and remaining data.

        :return: (key_string, other_data)
        """
        pass

    @abc.abstractmethod
    def on_data(self, peer, data):
        """
        Callback for when a binary blob of data is received from a peer.
        """
        pass

    @property
    def global_time(self):
        return self.my_peer.get_lamport_timestamp()

    def claim_global_time(self):
        """
        Increments the current global time by one and returns this value.
        """
        self.update_global_time(self.global_time + 1)
        return self.global_time

    def update_global_time(self, global_time):
        """
        Increase the local global time if the given GLOBAL_TIME is larger.
        """
        if global_time > self.global_time:
            self.my_peer.update_clock(global_time)
