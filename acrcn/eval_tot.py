import tensorflow as tf
import numpy as np
import scipy.misc
from scipy.misc import imsave
import sys
import time
from generator import rot_generator as generate
from tensorflow.contrib.tensorboard.plugins import projector
# from tensorflow.examples.tutorials.mnist import input_data
# mnist = input_data.read_data_sets("/media/hdd/hdd/data_backup/prannayk/MNIST_data/", one_hot=True)

total_size = 64000
batch_size = 64

class VAEGAN():
	"""docstring for VAEGAN, no parent class"""
	def __init__(self, batch_size = 16, image_shape= [28,28,3], embedding_size = 128,
			learning_rate = sys.argv[1:], motion_size = 4, num_class_motion=6, 
			num_class_image=13, frames=2, frames_input=2, total_size = 64000, video_create=False):
		self.batch_size = batch_size
		self.image_shape = image_shape
		self.image_input_shape = list(image_shape)
		self.image_create_shape = list(image_shape)
		self.frames_input = frames_input
		self.frames = frames
		self.image_input_shape[-1] *= self.frames_input
		self.image_create_shape[-1] *= self.frames
		self.num_class_image = num_class_image
		self.num_class_motion = num_class_motion + self.frames
		self.num_class = num_class_image
		self.embedding_size = embedding_size 
		self.zdimension = self.num_class
		self.motion_size = motion_size
		self.learning_rate = map(lambda x: float(x), learning_rate[:(len(learning_rate) - 2)])
		self.lambda_1 = 300
		self.lambda_2 = 200
		self.gan_scale = 50
		self.dim_1 = [self.image_shape[0], self.image_shape[1]]
		self.dim_2 = [self.image_shape[0] // 2, self.image_shape[1] // 2]
		self.dim_4 = [self.image_shape[0] // 4, self.image_shape[1] // 4]
		self.dim_8 = [self.image_shape[0] // 8, self.image_shape[1] // 8]
		self.dim_16 = [self.image_shape[0] // 16, self.image_shape[1] // 8]
		self.dim_channel = self.image_shape[-1]
		self.image_size = reduce(lambda x,y : x*y, image_shape)
		self.initializer = tf.random_normal_initializer(stddev=0.02)
		self.first_time = True
		self.device= "cpu:0"
		self.total_size = total_size
		self.batch_size = batch_size
		self.video_create = video_create
		self.wgan_scale = 1.2

	def learningR(self):
		return self.learning_rate

	def variable_summaries(self, var,name=None):
		with tf.name_scope("summaries_%s"%(name)):
			mean = tf.reduce_mean(var)
			tf.summary.scalar("mean", mean)
			with tf.name_scope("stddev"):
				stddev = tf.sqrt(tf.reduce_mean(tf.square(var - mean)))
			tf.summary.scalar("stddev", stddev)
			tf.summary.scalar("max", tf.reduce_max(var))
			tf.summary.scalar("min", tf.reduce_min(var))
			tf.summary.histogram("histogram",var)

	def normalize(self, X, reuse=False, name=None, flag=False):
		if not flag : 
			mean , vari = tf.nn.moments(X, [0], keep_dims =True)
		else:
			mean, vari = tf.nn.moments(X, [0,1,2], keep_dims=True)
		return tf.nn.batch_normalization(X, mean, vari, offset=None, 
			scale=None, variance_epsilon=1e-6, name=name)

	def gan_loss(self, X, Y, discriminator, X_in, Y_in, reuse=False, name=None, scope=tf.variable_scope("random_testing"), flag=True):
		if not flag : 
			return tf.reduce_mean(X)
		loss = tf.reduce_mean(Y) - tf.reduce_mean(X)
		epsilon = tf.random_normal([],0.0,1.0)
		mix = (X_in * epsilon) + ((1-epsilon) * Y_in)
		scope.reuse_variables()
		d_hat = discriminator(mix, scope=scope)
		grads = tf.gradients(d_hat, mix)
		ddx_sum = tf.sqrt(tf.reduce_sum(tf.square(grads), axis=1))
		ddx_loss = tf.reduce_mean(tf.square(ddx_sum - 1.0) * self.wgan_scale)
		return loss + ddx_loss
	def generate_batch(self):
		return generate(self.batch_size, self.frames,self.frames_input)
	def discriminate_image(self, image, zvalue=None, scope=tf.variable_scope("variable_scope")):
		if zvalue == None :
			zvalue = self.default_z
		with tf.device(self.device):
			ystack = tf.reshape(zvalue, [self.batch_size, 1,1,self.zdimension])
			yneed_1 = ystack*tf.ones([self.batch_size, self.dim_1[0] , self.dim_1[1], self.zdimension])
			yneed_2 = ystack*tf.ones([self.batch_size, self.dim_2[0], self.dim_2[1], self.zdimension])
			yneed_3 = ystack*tf.ones([self.batch_size, self.dim_4[0], self.dim_4[1], self.zdimension])
			yneed_4 = ystack*tf.ones([self.batch_size, self.dim_8[0], self.dim_8[1], self.zdimension])
			
			LeakyReLU = tf.contrib.keras.layers.LeakyReLU(alpha=0.2)

			image_proc = tf.concat(axis=3, 
				values=[self.normalize(image, flag=True), yneed_1])
			h1 = tf.layers.conv2d(image_proc, filters=8, kernel_size=[5,5],
				strides=[2,2], padding='SAME',
				activation=None,
				kernel_initializer=self.initializer,
				reuse=scope.reuse, name="conv_1")
			h1_relu = LeakyReLU(h1)
			h1_concat = self.normalize(tf.concat(axis=3, values=[h1_relu, yneed_2]))
			h2 = tf.layers.conv2d(h1_concat, filters=16, kernel_size=[5,5],
				strides=[1,1], padding='SAME',
				activation=None, 
				kernel_initializer=self.initializer,
				reuse=scope.reuse,name="conv_2")
			h2_relu = LeakyReLU(h2)
			h2_concat = self.normalize(tf.concat(axis=3, values=[h2_relu, yneed_2]))
			h3 = tf.layers.conv2d(h2_concat, filters=32, kernel_size=[5,5],
				strides=[2,2], padding='SAME',
				activation=None, 
				kernel_initializer=self.initializer,
				reuse=scope.reuse,name="conv_3")
			h3_relu = LeakyReLU(h3)
			h3_concat = self.normalize(tf.concat(axis=3, values=[h3_relu, yneed_3]))
			h4 = tf.layers.conv2d(h3_concat, filters=64, kernel_size=[5,5],
				strides=[1,1], padding='SAME',
				activation=None, 
				kernel_initializer=self.initializer,
				reuse=scope.reuse,name="conv_4")
			h4_relu = LeakyReLU(h4)
			h4_concat = self.normalize(tf.concat(axis=3, values=[h4_relu, yneed_3]))
			h5 = tf.layers.conv2d(h4_concat, filters=64, kernel_size=[5,5],
				strides=[2,2], padding='SAME',
				activation=None, 
				kernel_initializer=self.initializer,
				reuse=scope.reuse,name="conv_5")
			h5_relu = LeakyReLU(h3)
			h5_reshape = tf.reshape(h5, shape=[self.batch_size,self.dim_8[1]*self.dim_8[0]*64])
			h5_concat = self.normalize(tf.concat(axis=1, values=[h5_reshape, zvalue]))
			h6 = tf.layers.dense(h5_concat, units=256, 
				activation=None,
				kernel_initializer=self.initializer,
				name='dense_1',
				reuse=scope.reuse)
			h6_relu = LeakyReLU(h6)
			h6_concat = self.normalize(tf.concat(axis=1, values=[h6_relu, zvalue]))
			h7 = tf.layers.dense(h6_concat, units=1, 
				activation=None,
				kernel_initializer=self.initializer,
				name='dense_2',
				reuse=scope.reuse)
			return tf.nn.sigmoid(LeakyReLU(self.normalize(h5, name="last_normalize", reuse=scope.reuse)))
	def generate_image(self, embedding, zvalue, scope):
		with tf.device(self.device):
			ystack = tf.reshape(zvalue, shape=[self.batch_size, 1,1 , self.zdimension])
			yneed_1 = ystack*tf.ones([self.batch_size, self.dim_4[0], self.dim_4[1], self.zdimension])
			yneed_2 = ystack*tf.ones([self.batch_size, self.dim_2[0], self.dim_2[1], self.zdimension])
			yneed_3 = ystack*tf.ones([self.batch_size, self.dim_8[0], self.dim_8[1], self.zdimension])
			embedding = tf.concat(axis=1, values=[embedding, zvalue])
			h1 = tf.layers.dense(embedding, units=1280, activation=None,
				kernel_initializer=self.initializer, 
				name='dense_1', reuse=scope.reuse)
			h1_relu = tf.nn.relu(self.normalize(h1))
			h1_reshape = tf.reshape(h1_relu, shape=[self.batch_size, self.dim_8[0], self.dim_8[1], 64])
			h1_concat = tf.concat(axis=3, values=[h1_reshape,yneed_3])
			h2 = tf.layers.conv2d_transpose(inputs=h1_concat, filters = 64, 
				kernel_size=[5,5], strides=[2,2], padding='SAME', activation=None,
				kernel_initializer=self.initializer,
				reuse=scope.reuse,name='conv_1')
			h2_relu = tf.nn.relu(self.normalize(h2))
			h2_concat = tf.concat(axis=3, values=[h2_relu, yneed_1])
			h3 = tf.layers.conv2d_transpose(inputs=h2_concat, filters = 32, 
				kernel_size=[5,5], strides=[2,2], padding='SAME', activation=None,
				kernel_initializer=self.initializer,
				reuse=scope.reuse,name='conv_2')
			h3_relu = tf.nn.relu(self.normalize(h3))
			h3_concat = tf.concat(axis=3, values=[h3_relu, yneed_2])
			h4 = tf.layers.conv2d_transpose(inputs=h3_concat, filters = self.dim_channel, 
				kernel_size=[5,5], strides=[2,2], padding='SAME', activation=None,
				kernel_initializer=self.initializer,
				reuse=scope.reuse,name='conv_3')
			return tf.nn.sigmoid(h4)
	def encoder_image(self, image, scope):
		with tf.device(self.device):
			LeakyReLU = tf.contrib.keras.layers.LeakyReLU(alpha=0.2)
			image_proc = self.normalize(image,flag=True)
			h1 = tf.layers.conv2d(image_proc, filters=48, kernel_size=[4,4],
				strides=[2,2], padding='SAME',
				activation=None,
				kernel_initializer=self.initializer,
				reuse=scope.reuse, name="conv_1")
			h1_relu = self.normalize(LeakyReLU(h1))
			h2 = tf.layers.conv2d(h1_relu, filters=64, kernel_size=[4,4],
				strides=[2,2], padding='SAME',
				activation=None,
				kernel_initializer=self.initializer,
				reuse=scope.reuse, name="conv_2")
			h2_relu = self.normalize(LeakyReLU(h2))
			h3 = tf.layers.conv2d(h2_relu, filters=16, kernel_size=[4,4],
				strides=[2,2], padding='SAME',
				activation=None,
				kernel_initializer=self.initializer,
				reuse=scope.reuse, name="conv_3")
			h3_relu = self.normalize(LeakyReLU(h3))
			h3_reshape = tf.reshape(h3_relu, shape=[self.batch_size, self.dim_8[0]*self.dim_8[1]*16])
			h4 = tf.layers.dense(h3_reshape, units=self.embedding_size+self.num_class_image, 
				activation=None,
				kernel_initializer=self.initializer,
				name='dense_2',
				reuse=scope.reuse)
			return h4 # no activation over last layer of h4 
	def encoder_motion(self, motion_embedding, scope):
		with tf.device(self.device):
			h1 = tf.layers.dense(motion_embedding, units=512,
				activation=None, kernel_initializer=self.initializer,
				name="dense_1", reuse=scope.reuse)
			h1_relu = tf.nn.relu(self.normalize(h1))
			h2 = tf.layers.dense(h1, units=self.num_class_motion, 
				activation=None, kernel_initializer=self.initializer,
				name="dense_2", reuse=scope.reuse)
			h2_normalize = self.normalize(h2)
			h3 = tf.nn.softmax(h2)
			return h3
	def discriminate_encode(self, input_embedding, scope):
		h1 = tf.layers.dense(input_embedding, units=750,
			activation=None, kernel_initializer=self.initializer,
			name="dense_1", reuse=scope.reuse)
		h1_relu = tf.nn.relu(self.normalize(h1))
		h2 = tf.layers.dense(h1, units=750,
			activation=None, kernel_initializer=self.initializer, 
			name="dense_2", reuse=scope.reuse)
		h2_relu = tf.nn.relu(self.normalize(h2))
		h3 = tf.layers.dense(h2, units=1, 
			activation=None, kernel_initializer=self.initializer,
			name="dense_3", reuse=scope.reuse)
		return tf.nn.sigmoid(self.normalize(h3))
	def create_frames(self, image_input, x, z_s, z_c, image_class_input, text_label_input, z_t):
		with tf.variable_scope("encoder") as scope:
			if not self.first_time :
				scope.reuse_variables()
			encode = self.encoder_image(image_input, scope)
		with tf.variable_scope("text_encoder") as scope:
			if not self.first_time :
				scope.reuse_variables()
			text_encode = self.encoder_motion(text_label_input, scope)
		with tf.variable_scope("transformation") as scope:
			if not self.first_time : 
				scope.reuse_variables()
			encoder_alt = tf.layers.dense(encode[:,:self.embedding_size], units=int(encode.shape[-1]), reuse=scope.reuse, 
				kernel_initializer=self.initializer, use_bias=True, name="transformation")
		z_hat_s = encode[:,:self.embedding_size]
		z_hat_s_fut = encoder_alt[:,:self.embedding_size] # for transformation embedding to create video
		z_hat_c = tf.nn.softmax(encode[:,self.embedding_size:])
		z_hat_t = tf.nn.softmax(text_encode)
		z_hat_input = tf.concat(axis=1, values=[z_hat_s, z_hat_t])
		z_hat_input_fut = tf.concat(axis=1, values=[z_hat_s_fut, z_hat_t])
		with tf.variable_scope("generator") as scope:
			if not self.first_time :
				scope.reuse_variables()
			x_hat = self.generate_image(z_hat_input, z_hat_c, scope)
			scope.reuse_variables()
			x_hat_fut = self.generate_image(z_hat_input_fut, z_hat_c, scope)
			x_dash = self.generate_image(tf.concat(axis=1, values=[z_s, z_t]),z_c,scope)
			x_gen = self.generate_image(z_hat_input,z_hat_c, scope)
		with tf.variable_scope("image_discriminator") as scope:
			if not self.first_time :
				scope.reuse_variables()
			D_x_hat = self.discriminate_image(x_hat, z_hat_c, scope)
			scope.reuse_variables()
			D_x_hat_fut = self.discriminate_image(x_hat_fut, image_class_input, scope)
			D_x = self.discriminate_image(x, image_class_input, scope)
			D_x_dash = self.discriminate_image(x_dash, z_c,scope)
			D_x_gen = self.discriminate_image(x_gen, z_hat_c, scope)
			D_x_loss = self.gan_loss( D_x_hat, D_x, self.discriminate_image, x_hat, x, scope=scope)
			G_x_loss = self.gan_loss( D_x_hat, D_x, self.discriminate_image, x_hat, x, scope=scope, flag=False)
			D_x_loss += self.gan_loss( D_x_hat_fut, D_x, self.discriminate_image, x_hat_fut, x, scope=scope)
			G_x_loss += self.gan_loss( D_x_hat_fut, D_x, self.discriminate_image, x_hat_fut, x, scope=scope, flag=False)
			D_x_loss += self.gan_loss( D_x_dash, D_x, self.discriminate_image, x_dash, x, scope=scope)
			G_x_loss += self.gan_loss( D_x_dash, D_x, self.discriminate_image, x_dash, x, scope=scope, flag=False)
			D_x_loss += self.gan_loss( D_x_gen, D_x, self.discriminate_image, x_gen, x, scope=scope)
			G_x_loss += self.gan_loss( D_x_gen, D_x, self.discriminate_image, x_gen, x, scope=scope, flag=False)
		with tf.variable_scope("text_classifier") as scope:
			if not self.first_time :
				scope.reuse_variables()
			D_z_hat_t = self.discriminate_encode(z_hat_t,scope)
			scope.reuse_variables()
			D_z_t = self.discriminate_encode(z_t, scope)
			D_z_t_loss = self.gan_loss(D_z_hat_t, D_z_t, self.discriminate_encode, z_hat_t, z_t, scope=scope)
			G_z_t_loss = self.gan_loss(D_z_hat_t, D_z_t, self.discriminate_encode, z_hat_t, z_t, scope=scope, flag=True)
		with tf.variable_scope("image_classifier") as scope:
			if not self.first_time :
				scope.reuse_variables()
			D_z_hat_c = self.discriminate_encode(z_hat_c, scope)
			scope.reuse_variables()
			D_z_c = self.discriminate_encode(z_c, scope)
			D_z_real = self.discriminate_encode(image_class_input, scope)
			D_z_c_loss = self.gan_loss(D_z_hat_c, D_z_real, self.discriminate_encode,z_hat_c, image_class_input ,scope=scope)
			D_z_c_loss += self.gan_loss(D_z_c, D_z_real, self.discriminate_encode,z_c, image_class_input ,scope=scope)
			G_z_c_loss = self.gan_loss(D_z_hat_c, D_z_real, self.discriminate_encode,z_hat_c, image_class_input ,scope=scope, flag=True)
			G_z_c_loss += self.gan_loss(D_z_c, D_z_real, self.discriminate_encode,z_c, image_class_input ,scope=scope, flag=True)
		with tf.variable_scope("style_classifier") as scope:
			if not self.first_time :
				scope.reuse_variables()
			z_hat_s = z_hat_s[:,:embedding_size]
			z_hat_s_fut = z_hat_s_fut[:,:embedding_size]
			D_z_hat_s = self.discriminate_encode(z_hat_s[:,:embedding_size], scope=scope)
			scope.reuse_variables()
			D_z_hat_s_fut = self.discriminate_encode(z_hat_s_fut[:,:embedding_size], scope)
			D_z_s = self.discriminate_encode(z_s, scope)
			D_z_s_loss = self.gan_loss(D_z_hat_s, D_z_s, self.discriminate_encode,z_hat_s, z_hat_s ,scope=scope)
			D_z_s_loss += self.gan_loss(D_z_hat_s_fut, D_z_s, self.discriminate_encode,z_hat_s_fut, z_hat_s ,scope=scope)
			G_z_s_loss = self.gan_loss(D_z_hat_s, D_z_s, self.discriminate_encode,z_hat_s, z_hat_s ,scope=scope, flag=True)
			G_z_s_loss += self.gan_loss(D_z_hat_s_fut, D_z_s, self.discriminate_encode,z_hat_s_fut, z_hat_s ,scope=scope, flag=True)
		self.first_time = False
		return x_hat, x_hat_fut, D_x_loss, G_x_loss, D_z_t_loss, G_z_t_loss, D_z_c_loss, G_z_c_loss, D_z_s_loss, G_z_s_loss, encode
	def build_model(self):
		image_input = tf.placeholder(tf.float32, shape=[self.batch_size]+ self.image_input_shape)
		x = tf.placeholder(tf.float32, shape=[self.batch_size]+self.image_create_shape)
		x_old = tf.placeholder(tf.float32, shape=[self.batch_size]+self.image_create_shape)
		z_s = tf.placeholder(tf.float32, shape=[self.batch_size*self.frames, self.embedding_size])
		z_c = tf.placeholder(tf.float32, shape=[self.batch_size*self.frames, self.num_class_image])
		image_class_input = tf.placeholder(tf.float32, shape=[self.batch_size, self.num_class_image])
		text_label_input = tf.placeholder(tf.float32, shape=[self.batch_size, self.motion_size])
		z_t = tf.placeholder(tf.float32, shape=[self.batch_size*self.frames, self.num_class_motion])
		self.default_z = image_class_input
		placeholders = {
			'image_input' : image_input,
			'x' : x,
			'x_old' : x_old,
			'image_class_input' : image_class_input,
			'text_label_input' : text_label_input,
			'z_s' : z_s,
			'z_c' : z_c,
			'z_t' : z_t
		}
		list_values = [[],[],[],[],[],[],[],[],[],[],[],[],[],[]]
		next_image_input = image_input
		for i in range(self.frames):
			list_return = self.create_frames(next_image_input, x[:,:,:,self.dim_channel*i:self.dim_channel*i+self.dim_channel], 
				z_s[self.batch_size*i:self.batch_size*i+self.batch_size], z_c[self.batch_size*i:self.batch_size*i+self.batch_size], 
				image_class_input, text_label_input, z_t[self.batch_size*i:self.batch_size*i+self.batch_size])
			for count,item in enumerate(list_return):
				list_values[count].append(item)
			if self.video_create :
				next_image_input = tf.concat(axis=3, values=[next_image_input[:,:,:,self.dim_channel:], x[:,:,:,self.dim_channel*i:self.dim_channel*i+self.dim_channel]])
			else :
				next_image_input = tf.concat(axis=3, values=[next_image_input[:,:,:,self.dim_channel:], list_output[0]])

		x_hat = tf.concat(axis=3, values=list_values[0])
		x_hat_fut = tf.concat(axis=3, values=list_values[1])
		D_x_loss = tf.reduce_mean(tf.stack(axis=0, values=list_values[2]))
		G_x_loss = tf.reduce_mean(tf.stack(axis=0, values=list_values[3]))
		D_z_t_loss = tf.reduce_mean(tf.stack(axis=0, values=list_values[4]))
		G_z_t_loss = tf.reduce_mean(tf.stack(axis=0, values=list_values[5]))
		D_z_c_loss = tf.reduce_mean(tf.stack(axis=0, values=list_values[6]))
		G_z_c_loss = tf.reduce_mean(tf.stack(axis=0, values=list_values[7]))
		D_z_s_loss = tf.reduce_mean(tf.stack(axis=0, values=list_values[8]))
		G_z_s_loss = tf.reduce_mean(tf.stack(axis=0, values=list_values[9]))
		embedding = list_values[10][0]
		losses = dict()
		with tf.variable_scope("losses"):
			losses["reconstruction"] = tf.sqrt(tf.reduce_mean(tf.square(x-x_hat_fut))) + tf.sqrt(tf.reduce_mean(tf.square(x_old-x_hat)))
			losses["anti-reconstruction"] = tf.sqrt(tf.reduce_mean(tf.square(x_hat_fut - x_hat)))
			losses["disc_image_classifier"] = D_z_c_loss
			losses["gen_image_classifier"] = G_z_c_loss
			losses["disc_text_classifier"] = D_z_t_loss
			losses["gen_text_classifier"] = G_z_t_loss
			losses["disc_image_discriminator"] = D_x_loss*self.gan_scale + (self.lambda_2*losses["anti-reconstruction"])
			losses["generator_image"] = self.gan_scale*G_x_loss + (self.lambda_1*losses["reconstruction"]) 
			losses["generator_image_gan"] = self.gan_scale*G_x_loss + (self.lambda_1*losses["reconstruction"]) - (self.lambda_2*losses["anti-reconstruction"])
			losses["text_encoder"] = losses["gen_text_classifier"] + (losses["reconstruction"]*self.lambda_1) - (self.lambda_2*losses["anti-reconstruction"])
			losses["disc_style_classifier"] = D_z_s_loss
			losses["gen_style_classifier"] = G_z_s_loss
			losses["encoder"] = losses["gen_image_classifier"] + (self.lambda_1*losses["reconstruction"]) + losses["gen_style_classifier"] - (self.lambda_2*losses["anti-reconstruction"])
			losses["transformation"] = -losses["anti-reconstruction"]*self.lambda_2 + self.lambda_1*losses["reconstruction"] 
		self.variable_summaries(losses["reconstruction"],name="reconstruction_loss")
		self.variable_summaries(G_x_loss, name="Reconstruction_GAN_loss")
		self.variable_summaries(D_x_loss, name="Reconstruction_GAN_loss")
		self.variable_summaries(losses["anti-reconstruction"], name="anti-reconstruction-loss")
		print("Completed losses")
		variable_dict = dict()
		variable_dict["encoder"] = [i for i in filter(lambda x: x.name.startswith("encoder"), tf.trainable_variables())]
		variable_dict["transformation"] = [i for i in filter(lambda x: x.name.startswith("transformation"), tf.trainable_variables())]
		variable_dict["text_encoder"] = [i for i in filter(lambda x: x.name.startswith("text_encoder"), tf.trainable_variables())]
		variable_dict["generator"] = [i for i in filter(lambda x: x.name.startswith("generator"), tf.trainable_variables())]
		variable_dict["image_disc"] = [i for i in filter(lambda x: x.name.startswith("image_disc"), tf.trainable_variables())]
		variable_dict["image_class"] = [i for i in filter(lambda x: x.name.startswith("image_class"), tf.trainable_variables())]
		variable_dict["text_class"] = [i for i in filter(lambda x: x.name.startswith("text_class"), tf.trainable_variables())]
		variable_dict["style_class"] = [i for i in filter(lambda x: x.name.startswith("style_class"), tf.trainable_variables())]
		print("Completed weights")
		optimizer = dict()
		with tf.variable_scope("optimizers"):
			# encoder_adam = tf.train.AdamOptimizer(self.learning_rate[0],beta1=0.5,beta2=0.9)
			print("encoder")
			optimizer["encoder"] = tf.train.AdamOptimizer(self.learning_rate[0],beta1=0.5,beta2=0.9).minimize(losses["encoder"], var_list=variable_dict["encoder"])
			optimizer["transformation"] = tf.train.AdamOptimizer(self.learning_rate[0], beta1=0.5, beta2=0.9).minimize(losses["transformation"], var_list=variable_dict["transformation"])
			print("text_encoder")
			optimizer["text_encoder"] = tf.train.AdamOptimizer(self.learning_rate[1], beta1=0.5, beta2=0.9).minimize(losses["text_encoder"], var_list=variable_dict["text_encoder"])
			print("generator")
			optimizer["generator"] = tf.train.AdamOptimizer(self.learning_rate[0],beta1=0.5,beta2=0.9).minimize(losses["generator_image"], var_list=variable_dict["generator"])
			optimizer["generator_gan"] = tf.train.AdamOptimizer(self.learning_rate[0],beta1=0.5,beta2=0.9).minimize(losses["generator_image_gan"], var_list=variable_dict["generator"])
			optimizer["generator_reconstruction"] = tf.train.AdamOptimizer(self.learning_rate[0],beta1=0.5,beta2=0.9).minimize(self.lambda_1*losses["reconstruction"], var_list=variable_dict["generator"])
			print("disc_image")
			optimizer["discriminator"] = tf.train.AdamOptimizer(self.learning_rate[3],beta1=0.5, beta2=0.9).minimize(losses["disc_image_discriminator"], var_list=variable_dict["image_disc"])
			print("disc_non_image")
			optimizer["code_discriminator"] = tf.train.AdamOptimizer(self.learning_rate[4],beta1=0.5, beta2=0.9).minimize(losses["disc_image_classifier"], var_list=variable_dict["image_class"])
			optimizer["text_discriminator"] = tf.train.AdamOptimizer(self.learning_rate[5],beta1=0.5, beta2=0.9).minimize(losses["disc_text_classifier"], var_list=variable_dict["text_class"])
			optimizer["style_discriminator"] = tf.train.AdamOptimizer(self.learning_rate[6],beta1=0.5, beta2=0.9).minimize(losses["disc_style_classifier"], var_list=variable_dict["style_class"])
		print("Completed optimizers")
		return placeholders, optimizer, losses, x_hat, x_hat_fut, embedding

epoch = 600
embedding_size =128
motion_size=7
num_class_image=25
frames=5
frames_input = 3
num_class_motion = 7

def save_visualization(X, nh_nw=(batch_size,frames_input+frames), save_path='../results/%s/sample.jpg'%(sys.argv[4])):
	print(X.shape)
	X = morph(X)
	print(X.shape)
	h,w = X.shape[1], X.shape[2]
	img = np.zeros((h * nh_nw[0], w * nh_nw[1], 3))
	
	for n,x in enumerate(X):
		j = n // nh_nw[1]
		i = n % nh_nw[1]
		img[j*h:j*h+h, i*w:i*w+w, :] = x[:,:,:3]
	np.save("%s.%s"%(save_path.split(".")[0],".npy"), img)
	scipy.misc.imsave(save_path, img)

def frame_label(batch_size, frames):
	t = np.zeros([batch_size*frames, frames])
	for i in range(batch_size):
		for j in range(frames):
			t[i*frames + j,j] = 1
	return t
def morph(X):
	batch_size = int(X.shape[0])
	dim_channel = int(X.shape[-1]) // (frames_input+frames)
	print(dim_channel)
	h,w = map(lambda x: int(x), X.shape[1:3])
	img = np.zeros([(frames_input+frames)*batch_size,h,w,dim_channel])
	for i in range(batch_size):
		for t in range(frames_input+frames):
			img[i*(frames_input+frames) + t] = X[i,:,:,t*dim_channel:t*dim_channel+dim_channel]
	return img

def random_label(batch_size, size):
	t = np.random.choice(10, batch_size, replace=True)
	random = np.zeros(shape=[batch_size, size])
	for i in range(batch_size):
		random[i, int(t[i])] = 1
	return random	


def get_feed_dict(gan):
	feed_list = gan.generate_batch()
	return feed_list
def train_epoch(gan,tensor_writer,flag=False, initial=True):
	eptime = time.time()
	start_time = time.time()
	run =0 
	count = 0
	label_data = np.zeros([num_examples, motion_size])
	images = np.zeros([num_examples, 32,40,1])
	embedding_np = np.zeros([num_examples, 32*40])
	while run < num_examples:		
		feed_list = get_feed_dict(gan)
		label_data[run:run+batch_size] = feed_list[4]
		images[run:run+batch_size] = feed_list[0][:,:,:,:1]
		embedding_np[run:run+batch_size] = images[run:run+batch_size].reshape([batch_size,32*40])
		run+=batch_size
		count += 1
		if count % 10 == 0 or flag:
			print(time.time() - start_time)
			start_time = time.time() 
	print("Total time: " + str(time.time() - eptime))
	return embedding_np, images, label_data
def create_sprite_image(images):
	img_h = images.shape[1]
	img_w = images.shape[2]
	n_plots = int(np.ceil(np.sqrt(images.shape[0])))
	spriteimage = np.ones([img_h*n_plots, img_w*n_plots])

	for i in range(n_plots):
		for j in range(n_plots):
			this_filter = i*n_plots + j
			if this_filter < images.shape[0]:
				print(np.mean(images[this_filter]))
				this_img = images[this_filter]
				spriteimage[i*img_h:(i+1) * img_h,
				j * img_w:(j + 1) * img_w ] = this_img[:,:,0]*255.
	imsave("../embeddings/testmain.jpg",spriteimage)
def one_hot(X):
	for i in range(X.shape[0]):
		if X[i] == 1:
			return i


image_sample, image_old,image_gen,image_labels, text_labels, _ = generate(batch_size, frames, frames_input)
save_visualization(np.concatenate([image_sample,image_gen],axis=3), save_path='../results/acrcn/32/%s/sample.jpg'%(sys.argv[-2]))
gan = VAEGAN(batch_size=batch_size, embedding_size=embedding_size, image_shape=[32,40,1], motion_size=motion_size,  
	num_class_motion=num_class_motion, num_class_image=num_class_image, frames=frames, video_create=True, frames_input=frames_input)
num_examples=640
#placeholders,optimizers, losses, x_hat, x_hat_fut, embedding = gan.build_model()
print("Starting session")
session = tf.InteractiveSession(config=tf.ConfigProto(log_device_placement=False))
model_name = "/extra_data/prannay/models/large_acnrcn.ckpt"
merged = tf.summary.merge_all()
#train_writer = tf.summary.FileWriter("../logs/%s/"%(sys.argv[-2]))
tf.global_variables_initializer().run()
#saver.restore(session,model_name)
print("Running code: ")
epoch = int(sys.argv[-1])
diter = 5
num_examples = 16000
summary_writer = tf.summary.FileWriter("/users/gpu/prannay/vgan/embeddings")
embedding_np, images, label_data = train_epoch(gan, summary_writer)
create_sprite_image(images)
np.save("../embeddings/motion.npy", embedding_np)
with open("../embeddings/motiondata.tsv", mode="w") as fil:
	fil.write("Index\tLabel\n")
	for i, label in enumerate(label_data):
		fil.write("%d\t%d\n"%(i, one_hot(label)))
embedding_tensor = tf.Variable(embedding_np)
saver = tf.train.Saver()
init_embedding = tf.variables_initializer([embedding_tensor])
session.run(init_embedding)
config = projector.ProjectorConfig()
embedding = config.embeddings.add()
embedding.tensor_name = embedding_tensor.name
embedding.metadata_path = "../embeddings/metadata.tsv"
embedding.sprite.image_path = "../embeddings/testmain.jpg"
embedding.sprite.single_image_dim.extend([32,40])
print("here")
projector.visualize_embeddings(summary_writer, config)
saver.save(session, "../embeddings/model.ckpt",1)
print("writing file")
with open("../embeddings/metadata.tsv", mode="w") as fil:
	fil.write("Index\tLabel\n")
	for i, label in enumerate(label_data):
		fil.write("%d\t%d\n"%(i, one_hot(label)))
