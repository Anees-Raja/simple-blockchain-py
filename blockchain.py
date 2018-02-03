import hashlib
import json
from time import time
from uuid import uuid4
from flask import Flask, jsonify, request
from urllib.parse import urlparse
import requests

class Blockchain(object):
	def __init__(self):
		self.chain = []
		self.current_transactions = []
		self.nodes = set()

		# genesis block creation
		self.new_block(previous_hash=1, proof=100)

	# Handle new block
	def new_block(self, proof, previous_hash=None):
		"""
		A block takes the following params:
		proof(int) <- get it from the PoW Algorithm,
		previous_hash(str) <- verify this block is being added to a valid block,
		return(dict) <- the block is a returned object
		"""

		block = {
			'index': len(self.chain) + 1,
			'timestamp': time(),
			'transaction': self.current_transactions,
			'proof': proof,
			'previous_hash': previous_hash or self.hash(self.chain[-1]),
		}

		# reset list of transactions
		self.current_transactions = []

		self.chain.append(block)
		return block
	
	# Handle new transaction
	def new_transaction(self, sender, recipient, amount):
		"""
		A new transaction takes the following params:
		sender(str): sender's address,
		recipient(str): recipients address,
		amount(int): amount,
		return(int): Index of the block that will hold this transaction
		"""
		self.current_transactions.append({
			'sender': sender,
			'recipient': recipient,
			'amount': amount,
		})

		return self.last_block['index'] + 1

	# Handle new node registration
	def register_node(self, address):
		"""
		Add a new node

		address(str): ip address of node
		return: none
		"""

		parsed_url = urlparse(address)
		self.nodes.add(parsed_url.netloc)
	
	# Check chain validity.
	def valid_chain(self, chain):
		"""
		Determine if current chain is valid

		chain(list): A blockchain
		return(bool): True == Valid, False == Invalid
		"""

		last_block = chain[0]
		current_index = 1

		while current_index < len(chain):
			block = chain[current_index]
			print(f'{last_block}')
			print(f'{block}')
			print("\n--------------------\n")

			# Hash of current block valid?
			if block['previous_hash'] != self.hash(last_block):
				return False

			# Check if proof is correct
			if not self.valid_proof(last_block['proof'], block['proof']):
				return False
			
			last_block = block
			current_index += 1
		
		return True

	def resolve_conflicts(self):
		"""
		Consensus algorithm to determine the chain that nodes should follow, replaces all nodes blockchain's
		with the longest valid chain.

		return(bool): True = chain replaced, False = no replacement (this is the longest valid chain)
		"""

		neighbours = self.nodes
		new_chain = None

		# Looking for chains longer than max_length
		max_length = len(self.chain)

		# Get all the nodes in the network
		for node in neighbours:
			response = requests.get(f'http://{node}/chain')

			# Get the chain and its length from the node
			if response.status_code == 200:
				length = response.json()['length']
				chain = response.json()['chain']

				# If the chain is longer and is a valid chain
				if length > max_length and self.valid_chain(chain):
					max_length = length
					new_chain = chain
		
		# If we found a longer valid chain we replace ours with it
		if new_chain:
			self.chain = new_chain
			return True
		
		# If no longer valid chain found
		return False
	
	@property
	def last_block(self):
		return self.chain[-1]

	@staticmethod
	def hash(block):
		"""
		Creates a SHA-256 hash of a Block

		block(dict): Block
		return(str): hash
		"""

		#dictionaries must be order everytime for consistency
		block_string = json.dumps(block, sort_keys=True).encode()
		return hashlib.sha256(block_string).hexdigest()

	# Find the proof
	def proof_of_work(self, last_proof):
		"""
		Current Algo:
		- Find a number 'p' such that hash(p*p') is a hash with 4 leading 0's, where p is the previous p'
		- p is the previous proof, and p' is the new proof

		last_proof(int)
		return(int)
		"""

		proof = 0
		# while not a valid proof
		while self.valid_proof(last_proof, proof) is False:

			# search for correct proof
			proof +=1
		
		return proof
	
	@staticmethod
	# Validate proofs
	def valid_proof(last_proof, proof):
		"""
		Validates the proof: Does hash(last_proof, proof) contain 4 leading 0's?

		last_proof(int): previous proof
		proof(int): current proof <- this is being validated
		return(bool): Correct == True, Wrong == False
		"""

		guess = f'{last_proof}{proof}'.encode()
		guess_hash = hashlib.sha256(guess).hexdigest()

		# Adjust difficulty by adding things
		return guess_hash[:4] == "0000"

# Instantiate our Node
app = Flask(__name__)

# Generate a globally unique address for this node
node_identifier = str(uuid4()).replace('-', '')

# Instantiate the Blockchain
blockchain = Blockchain()

# Mining endpoint
@app.route('/mine', methods=['GET'])
def mine():
	# Run proof of work algorith to calculate next proof
	last_block = blockchain.last_block
	last_proof = last_block['proof']
	proof = blockchain.proof_of_work(last_proof)

	# Give miner reward, 0 = mining reward
	blockchain.new_transaction(
		sender="0",
		recipient=node_identifier,
		amount=1,
	)

	# Add new block to chain
	previous_hash = blockchain.hash(last_block)
	block = blockchain.new_block(proof, previous_hash)

	response = {
		'message': "New block FORGED",
		'index': block['index'],
		'transactions': block['transactions'],
		'proof': block['proof'],
		'previous_hash': block['previous_hash'],
	}

	return jsonify(response), 200

# Transaction endpoint
@app.route('/transactions/new', methods=['POST'])
def new_transaction():
	values = request.get_json()

	# Check that the data has required fields
	required = ['sender', 'recipient', 'amount']
	if not all(k in values for k in required):
		return 'Missing values', 400
	
	# Create a new transaction
	index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'])

	response = {'message': f'Transaction will be added to Block {index}' }
	return jsonify(response), 201

@app.route('/chain', methods=['GET'])
def full_chain():
	response = {
		'chain': blockchain.chain,
		'length': len(blockchain.chain),
	}
	return jsonify(response), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
	values = request.get_json()

	nodes = values.get('nodes')

	if nodes is None:
		return "Error: Please supply a valid list of nodes", 400
	
	for node in nodes:
		blockchain.register_node(node)
	
	response = {
		'message': 'New nodes have been added',
		'total_nodes': list(blockchain.nodes),
	}
	
	return jsonify(response), 201

@app.route('/nodes/resolve', methods=['GET'])
def consensus():
	replaced = blockchain.resolve_conflicts()

	if replaced:
		response = {
			'message': 'Our chain was replaced',
			'new_chain': blockchain.chain
		}
	else:
		response = {
			'message': 'Our chain is authoritative',
			'chain': blockchain.chain
		}
	
	return jsonify(response), 200



if __name__=='__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='port to listen on')
    args = parser.parse_args()
    port = args.port

    app.run(host='0.0.0.0', port=port)