import struct

from hashlib import sha1
from base64 import b64encode, b64decode
from twisted.internet.defer import inlineCallbacks

from .rest_peer_communication import HTTPGetRequesterDHT
from ...attestation.trustchain.test_block import TestBlock
from ...mocking.rest.base import RESTTestBase
from ...mocking.rest.rest_peer_communication import string_to_url
from ...mocking.rest.rest_api_peer import RestTestPeer
from ...mocking.rest.comunities import TestDHTCommunity, TestTrustchainCommunity
from ....attestation.trustchain.payload import HalfBlockPayload
from ....attestation.trustchain.community import TrustChainCommunity
from ....dht.community import DHTCommunity, MAX_ENTRY_SIZE
from ....REST.dht_endpoint import DHTBlockEndpoint
from ....messaging.serialization import Serializer


class TestDHTEndpoint(RESTTestBase):
    """
    Class for testing the DHT Endpoint in the REST API of the IPv8 object
    """

    def setUp(self):
        super(TestDHTEndpoint, self).setUp()
        self.initialize([(2, RestTestPeer)], HTTPGetRequesterDHT(), None)
        self.serializer = Serializer()

    def create_new_peer(self, peer_cls, port, *args, **kwargs):
        self._create_new_peer_inner(peer_cls, port, [TestDHTCommunity, TestTrustchainCommunity], *args, **kwargs)

    @inlineCallbacks
    def publish_to_DHT(self, peer, key, data, numeric_version):
        """
        Publish data to the DHT via a peer

        :param peer: the peer via which the data is published to the DHT
        :param key: the key of the added data
        :param data: the data itself; should be a string
        :param numeric_version: the version of the data
        :return: None
        """
        version = struct.pack("H", numeric_version)

        for i in range(0, len(data), MAX_ENTRY_SIZE - 3):
            blob_chunk = version + data[i:i + MAX_ENTRY_SIZE - 3]
            yield peer.get_overlay_by_class(DHTCommunity).store_value(key, blob_chunk)

    def deserialize_payload(self, serializables, data):
        """
        Deserialize data

        :param serializables: the list of serializable formats
        :param data: the serialized data
        :return: The payload obtained from deserializing the data
        """
        payload = self.serializer.unpack_to_serializables(serializables, data)
        return payload[:-1][0]

    @inlineCallbacks
    def test_added_block_explicit(self):
        """
        Test the publication of a block which has been added by hand to the DHT
        """
        param_dict = {
            'port': self.nodes[0].port,
            'interface': self.nodes[0].interface,
            'endpoint': 'dht/block',
            'public_key': string_to_url(b64encode(self.nodes[0].get_keys()['my_peer'].mid))
        }
        # Introduce the nodes
        yield self.introduce_nodes(DHTCommunity)

        # Manually add a block to the Trustchain
        original_block = TestBlock()
        hash_key = sha1(self.nodes[0].get_keys()['my_peer'].mid + DHTBlockEndpoint.KEY_SUFFIX).digest()

        yield self.publish_to_DHT(self.nodes[0], hash_key, original_block.pack(), 4536)

        # Get the block through the REST API
        response = yield self._get_style_requests.make_dht_block(param_dict)
        self.assertTrue('block' in response and response['block'], "Response is not as expected: %s" % response)
        response = b64decode(response['block'])

        # Reconstruct the block from what was received in the response
        payload = self.deserialize_payload((HalfBlockPayload, ), response)
        reconstructed_block = self.nodes[0].get_overlay_by_class(TrustChainCommunity).get_block_class(payload.type) \
            .from_payload(payload, self.serializer)

        self.assertEqual(reconstructed_block, original_block, "The received block was not the one which was expected")

    @inlineCallbacks
    def test_added_block_implicit(self):
        """
        Test the publication of a block which has been added implicitly to the DHT
        """
        param_dict = {
            'port': self.nodes[1].port,
            'interface': self.nodes[1].interface,
            'endpoint': 'dht/block',
            'public_key': string_to_url(b64encode(self.nodes[0].get_keys()['my_peer'].mid))
        }
        # Introduce the nodes
        yield self.introduce_nodes(DHTCommunity)

        publisher_pk = self.nodes[0].get_overlay_by_class(TrustChainCommunity).my_peer.public_key.key_to_bin()

        yield self.nodes[0].get_overlay_by_class(TrustChainCommunity).create_source_block(b'test', {})
        original_block = self.nodes[0].get_overlay_by_class(TrustChainCommunity).persistence.get(publisher_pk, 1)
        yield self.deliver_messages()

        # Get the block through the REST API
        response = yield self._get_style_requests.make_dht_block(param_dict)
        self.assertTrue('block' in response and response['block'], "Response is not as expected: %s" % response)
        response = b64decode(response['block'])

        # Reconstruct the block from what was received in the response
        payload = self.deserialize_payload((HalfBlockPayload,), response)
        reconstructed_block = self.nodes[0].get_overlay_by_class(TrustChainCommunity).get_block_class(payload.type)\
            .from_payload(payload, self.serializer)

        self.assertEqual(reconstructed_block, original_block, "The received block was not the one which was expected")

    @inlineCallbacks
    def test_latest_block(self):
        """
        Test the retrieval of the latest block via the DHT, when there is
        more than one block in the DHT under the same key
        """
        param_dict = {
            'port': self.nodes[1].port,
            'interface': self.nodes[1].interface,
            'endpoint': 'dht/block',
            'public_key': string_to_url(b64encode(self.nodes[0].get_keys()['my_peer'].mid))
        }
        # Introduce the nodes
        yield self.introduce_nodes(DHTCommunity)

        # Manually add a block to the Trustchain
        original_block_1 = TestBlock(transaction={1: 'asd'})
        original_block_2 = TestBlock(transaction={1: 'mmm'})
        hash_key = sha1(self.nodes[0].get_keys()['my_peer'].mid + DHTBlockEndpoint.KEY_SUFFIX).digest()

        # Publish the two blocks under the same key in the first peer
        yield self.publish_to_DHT(self.nodes[0], hash_key, original_block_1.pack(), 4536)
        yield self.publish_to_DHT(self.nodes[0], hash_key, original_block_2.pack(), 7636)

        # Get the block through the REST API from the second peer
        response = yield self._get_style_requests.make_dht_block(param_dict)
        self.assertTrue('block' in response and response['block'], "Response is not as expected: %s" % response)
        response = b64decode(response['block'])

        # Reconstruct the block from what was received in the response
        payload = self.deserialize_payload((HalfBlockPayload,), response)
        reconstructed_block = self.nodes[0].get_overlay_by_class(TrustChainCommunity).get_block_class(
            payload.type).from_payload(payload, self.serializer)

        self.assertEqual(reconstructed_block, original_block_2, "The received block was not equal to the latest block")
        self.assertNotEqual(reconstructed_block, original_block_1, "The received block was equal to the older block")

    @inlineCallbacks
    def test_block_duplication(self):
        """
        Test that a block which has already been pubished in the DHT will not be republished again; i.e. no
        duplicate blocks in the DHT under different (embedded) versions.
        """
        # Introduce the nodes
        yield self.introduce_nodes(DHTCommunity)

        # Manually create and add a block to the TrustChain
        original_block = TestBlock(key=self.nodes[0].get_keys()['my_peer'].key)
        self.nodes[0].get_overlay_by_class(TrustChainCommunity).persistence.add_block(original_block)

        # Publish the node to the DHT
        hash_key = sha1(self.nodes[0].get_keys()['my_peer'].mid + DHTBlockEndpoint.KEY_SUFFIX).digest()

        result = self.nodes[0].get_overlay_by_class(DHTCommunity).storage.get(hash_key)
        self.assertEqual(result, [], "There shouldn't be any blocks for this key")

        yield self.publish_to_DHT(self.nodes[0], hash_key, original_block.pack(), 4536)

        result = self.nodes[0].get_overlay_by_class(DHTCommunity).storage.get(hash_key)
        self.assertNotEqual(result, [], "There should be at least one chunk for this key")

        chunk_number = len(result)

        # Force call the method which publishes the latest block to the DHT and check that it did not affect the DHT
        self.nodes[0].get_overlay_by_class(TrustChainCommunity) \
            .notify_listeners(TestBlock(TrustChainCommunity.UNIVERSAL_BLOCK_LISTENER))

        # Query the DHT again
        result = self.nodes[0].get_overlay_by_class(DHTCommunity).storage.get(hash_key)
        self.assertEqual(len(result), chunk_number, "The contents of the DHT have been changed. This should not happen")
