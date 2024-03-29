import sys
import os
import logging
from collections import Counter
import datetime as dt

import tqdm
import fire
import numpy as np
from keras.optimizers import SGD, Adam, RMSprop
from keras.preprocessing.image import ImageDataGenerator
from keras.layers import Dropout, Flatten, Dense, Input
from keras.models import Model, Sequential
from keras import applications
from keras import backend as K

from settings import BASEPATH, PRETRAINED_PATH

stdout_handler = logging.StreamHandler(sys.stdout)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(filename)s:%(funcName)s:%(lineno)d] %(levelname)s - %(message)s',
    handlers=[stdout_handler]
)
logger = logging.getLogger('keras')


def make_optimiser(name="adam", learning_rate=0.0001, **kwargs):
    """
    Helper to create an optimiser from the command line.
    :param name: name of optimisers
    :param learning_rate: learning rate of optimiser
    :param kwargs: kwargs that can be passed along to keras optmiser
    :return:
    """
    if name not in ["adam", "rsmprop", "sgd"]:
        raise ValueError("name needs to be either adam, rsmprop or sgd")
    optimizers = {
        "adam": Adam(lr=learning_rate, **kwargs),
        "rsmprop": RMSprop(lr=learning_rate, **kwargs),
        "sgd": SGD(lr=learning_rate, **kwargs)
    }
    logger.debug(f"optimiser is of type {name} with lr {learning_rate}")
    return optimizers[name]


def get_pretrained_model(model, img_size):
    possible_names = ["vgg16", "vgg19", "mobilenet", "xception"]
    if model not in possible_names:
        raise ValueError(f"model needs to be either {possible_names}")
    logger.debug(f"backend for model is {model}")
    width, height = img_size
    if K.image_data_format() == 'channels_first':
        input_shape = (3, width, height)
    else:
        input_shape = (width, height, 3)
    logger.debug(f"backend suggests that we have the following input shape: {input_shape}")
    models = {
        "vgg16": applications.VGG16(input_shape=input_shape, include_top=False, weights='imagenet'),
        "vgg19": applications.VGG19(input_shape=input_shape, include_top=False, weights='imagenet'),
        "mobilenet": applications.MobileNet(input_shape=input_shape, include_top=False, weights='imagenet'),
        "xception": applications.Xception(input_shape=input_shape, include_top=False, weights='imagenet')
    }
    return models[model]


def get_image_generator(kind="random"):
    if kind not in ["random", "very-random", "not-random"]:
        raise ValueError("kind needs to be in `random`, `very-random`, `not-random`")
    logger.debug(f"making image generator kind={kind}")
    if kind == "not-random":
        return ImageDataGenerator(rescale=1. / 255)
    if kind == "random":
        return ImageDataGenerator(
            rescale=1. / 255,
            shear_range=0.1,
            zoom_range=0.1)
    if kind == "very-random":
        return ImageDataGenerator(
            rescale=1. / 255,
            shear_range=0.2,
            zoom_range=0.2,
            horizontal_flip=True)


def get_folders(dataset="catdog"):
    train_data_dir = os.path.join(BASEPATH, dataset, 'train')
    validation_data_dir = os.path.join(BASEPATH, dataset, 'validation')
    logger.debug(f"train_data_dir: {train_data_dir}")
    logger.debug(f"validation_data_dir: {validation_data_dir}")
    return train_data_dir, validation_data_dir


def make_pretrained_filenames(dataset, generator, model, n_img, img_size, npy=True):
    base_name = f"{dataset}-{model}-{generator}-{n_img}-{'x'.join([str(i) for i in img_size])}"
    names = []
    for settype in ['train', 'valid']:
        for xy in ['data', 'label']:
            names.append(f"{base_name}-{settype}-{xy}")
    if npy:
        return [_ + ".npy" for _ in names]
    return names


def make_pretrained_weights(dataset="catdog", generator="random", class_mode="binary",
                            model="vgg16", n_img=100, img_size=(224, 224)):
    filename = make_pretrained_filenames(dataset, generator, model, n_img, img_size, npy=False)
    x_train_fname, y_train_fname, x_valid_fname, y_valid_fname = filename

    logger.debug("about to make pretrained weights")
    datagen = get_image_generator(kind=generator)
    train_folder, valid_folder = get_folders(dataset=dataset)
    # TODO make this faster because 1 at a time
    # TODO that is really asking for overhead, right ?
    train_generator = datagen.flow_from_directory(
        train_folder,
        target_size=img_size,
        batch_size=1,
        class_mode=class_mode)
    valid_generator = datagen.flow_from_directory(
        valid_folder,
        target_size=img_size,
        batch_size=1,
        class_mode=class_mode)
    x_shape = [n_img] + list(train_generator.image_shape)
    y_shape = (n_img,)
    logger.debug("about to generate datasets for training-set of pretrained model")
    x_train = np.ones(shape=x_shape)
    y_train = np.ones(shape=y_shape)
    x_valid = np.ones(shape=x_shape)
    y_valid = np.ones(shape=y_shape)

    logger.debug(f"train data to have shape {x_train.shape}")
    logger.debug(f"train labels to have shape {y_train.shape}")
    logger.debug(f"validation data to have shape {x_valid.shape}")
    logger.debug(f"validation labels to have shape {y_valid.shape}")
    for i in tqdm.tqdm(range(n_img)):
        img_data_train, label_data_train = next(train_generator)
        img_data_valid, label_data_valid = next(valid_generator)
        x_train[i, :] = img_data_train.squeeze()
        y_train[i] = label_data_train.squeeze()
        x_valid[i, :] = img_data_valid.squeeze()
        y_valid[i] = label_data_valid.squeeze()
    logger.debug("train/validation input arrays has been prepared")
    logger.debug(f"train labels have following counts: {Counter(np.sort(y_train))}")
    logger.debug(f"valid labels have following counts: {Counter(np.sort(y_valid))}")

    base_model = get_pretrained_model(model=model, img_size=img_size)
    logger.debug(f"about to apply {model} to train data")
    tick = dt.datetime.now()
    pretrained_train = base_model.predict(x_train, verbose=1)

    logger.debug(f"predicting took {(dt.datetime.now() - tick).seconds}s or {(dt.datetime.now() - tick)} time")
    data_fp_x_train = os.path.join(PRETRAINED_PATH, x_train_fname)
    data_fp_y_train = os.path.join(PRETRAINED_PATH, y_train_fname)
    np.save(data_fp_x_train, pretrained_train)
    logger.debug(f"data has been written over at {data_fp_x_train}")
    np.save(data_fp_y_train, y_train)
    logger.debug(f"data has been written over at {data_fp_y_train}")

    logger.debug(f"about to apply {model} to validation data")
    tick = dt.datetime.now()
    pretrained_valid = base_model.predict(x_valid, verbose=1)
    logger.debug(f"predicting took {(dt.datetime.now() - tick).seconds}s or {(dt.datetime.now() - tick)} time")
    data_fp_x_valid = os.path.join(PRETRAINED_PATH, x_valid_fname)
    data_fp_y_valid = os.path.join(PRETRAINED_PATH, y_valid_fname)
    np.save(data_fp_x_valid, pretrained_valid)
    logger.debug(f"data has been written over at {data_fp_x_valid}")
    np.save(data_fp_y_valid, y_valid)
    logger.debug(f"data has been written over at {data_fp_y_valid}")


def get_pretrained_weights(dataset="catdog", generator="random", class_mode="binary",
                           model="mobilenet", n_img=10, img_size=(224, 224)):
    filenames = make_pretrained_filenames(dataset, generator, model, n_img, img_size, npy=True)
    for name in filenames:
        if not os.path.exists(os.path.join(PRETRAINED_PATH, name)):
            logger.debug(f"{os.path.join(PRETRAINED_PATH, name)} does not exist! creating .npz files.")
            make_pretrained_weights(dataset, generator, class_mode, model, n_img, img_size)

    x_train_fpath, y_train_fpath, x_valid_fpath, y_valid_fpath = [os.path.join(PRETRAINED_PATH, _) for _ in filenames]
    x_train = np.load(x_train_fpath)
    y_train = np.load(y_train_fpath)
    x_valid = np.load(x_valid_fpath)
    y_valid = np.load(y_valid_fpath)
    logger.debug("pretrained weight files have been found and loaded")
    for i in [os.path.join(PRETRAINED_PATH, _) for _ in filenames]:
        logger.debug(f"loaded file {i}")
    logger.debug(f"train data has shape: {x_train.shape}")
    logger.debug(f"valid data has shape: {x_valid.shape}")
    logger.debug(f"train labels have following counts: {Counter(np.sort(y_train))}")
    logger.debug(f"valid labels have following counts: {Counter(np.sort(y_valid))}")
    return x_train, y_train, x_valid, y_valid


def final_layers_model(input_shape, hidden_layer=10, dropout=0.5):
    logger.debug(f"creating model for image shape {input_shape}")
    img_input = Input(shape=input_shape[1:])
    x = Flatten()(img_input)
    x = Dense(hidden_layer, activation="relu")(x)
    x = Dropout(dropout)(x)
    x = Dense(1, activation="sigmoid", name="superfinallayer")(x)
    model = Model(img_input, x)
    return model

if __name__ == "__main__":
    fire.Fire(get_pretrained_weights)
