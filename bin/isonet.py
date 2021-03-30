#!/usr/bin/env python3
import fire
import logging
import os
from IsoNet.util.dict2attr import Arg,check_args
from IsoNet.util.deconvolution import tom_deconv_tomo
import sys
from IsoNet.preprocessing.cubes import mask_mesh_seeds
from fire import core
class ISONET:
    """
    ISONET: Train on tomograms and Predict to restore missing-wedge\n
    please run one of the following commands:
    isonet.py deconv
    isonet.py make_mask
    isonet.py refine
    isonet.py predict
    """
    def refine(self,
        input_dir: str = None,
        gpuID: str = '0,1,2,3',
        mask_dir: str= None,
        iterations: int = 50,
        data_dir: str = "data",
        pretrained_model = None,
        log_level: str = "info",
        continue_iter: int = 0,

        cube_size: int = 64,
        crop_size: int = 96,
        ncube: int = 1,
        preprocessing_ncpus: int = 16,

        epochs: int = 10,
        batch_size: int = 8,
        steps_per_epoch: int = 100,

        noise_level:  float= 0.05,
        noise_start_iter: int = 15,
        noise_pause: int = 5,

        drop_out: float = 0.3,
        convs_per_depth: int = 3,
        kernel: tuple = (3,3,3),
        pool: tuple = None,
        unet_depth: int = 3,
        filter_base: int = 64,
        batch_normalization: bool = False,
        normalize_percentile: bool = True,
    ):
        """
        Extract subtomogram and train neural network to correct missing wedge on generated subtomos
        :param input_dir: (None) directory containing tomogram(s) from which subtomos are extracted; format: .mrc or .rec
        :param mask_dir: (None) folder containing mask files, Eash mask file corresponds to one tomogram file, usually basename-mask.mrc
        :param gpuID: (0,1,2,3) The ID of gpu to be used during the training. e.g 0,1,2,3.
        :param pretrained_model: (None) A trained neural network model in ".h5" format to start with.
        :param iterations: (50) Number of training iterations.
        :param data_dir: (data) Temperary folder to save the generated data used for training.
        :param log_level: (info) debug level
        :param continue_iter: (0) Which iteration you want to start from?

        ************************Subtomo extraction settings************************

        :param cube_size: (64) Size of training cubes, this size should be divisible by 2^unet_depth.
        :param crop_size: (96) Size of cubes to impose missing wedge. Should be same or larger than size of cubes. Recommend 1.5 times of cube size
        :param ncube: (1) Number of cubes generated for each tomogram. Because each sampled subtomogram rotates 16 times, the actual number of subtomograms for trainings is ncube*16.
        :param preprocessing_ncpus: (16) Number of cpu for preprocessing.

        ************************Training settings************************

        :param epochs: (10) Number of epoch for each iteraction.
        :param batch_size: (8) Size of the minibatch.
        :param steps_per_epoch: (100) Step per epoch. A good estimation of this value is tomograms * ncube * 16 / batch_size *0.9.")

        ************************Denoise settings************************

        :param noise_level: (0.05) Level of noise STD(added noise)/STD(data) to start with. Set zero to disable noise reduction.
        :param noise_start_iter: (15) Iteration that start to add trainning noise.
        :param noise_pause: (5) Iters trainning noise remain at one level. The noise_level in each iteraion is defined as (((num_iter - noise_start_iter)//noise_pause)+1)*noise_level

        ************************Network settings************************

        :param drop_out: (0.3) Drop out rate to reduce overfitting.
        :param convs_per_depth: (3) Number of convolution layer for each depth.
        :param kernel: (3,3,3) Kernel for convolution
        :param unet_depth: (3) Number of convolution layer for each depth.
        :param filter_base: (64) The base number of channels after convolution
        :param batch_normalization: (False) Sometimes batch normalization may induce artifacts for extreme pixels in the first several iterations. Those could be restored in further iterations.
        :param normalize_percentile: (True) Normalize the 5 percent and 95 percent pixel intensity to 0 and 1 respectively. If this is set to False, normalize the input to 0 mean and 1 standard dievation.

        Typical training strategy:
        1. Train tomo with no pretrained model
        2. Continue train with previous interupted model
        3. Continue train with pre-trained model
        """

        from IsoNet.bin.refine import run

        d = locals()
        d_args = Arg(d)
        if d_args.log_level == "debug":
            logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',datefmt="%H:%M:%S",level=logging.DEBUG)
        else:
            logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',datefmt="%H:%M:%S",level=logging.INFO)
        # logging.basicConfig(level=logging.WARNING,format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
        # datefmt='%Y-%m-%d:%H:%M:%S')
        #if d_args.log_level == "debug":
        # logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger('IsoNet.bin.refine')
        d_args.only_extract_subtomos = False
        run(d_args)

    def predict(self, mrc_file: str, output_file: str, model: str, gpuID: str = None, cube_size:int=64,crop_size:int=96, batch_size:int=8,norm: bool=True,log_level: str="debug"):
        """
        Predict tomograms using trained model including model.json and weight(xxx.h5)
        :param mrc_file: path to tomogram, format: .mrc or .rec
        :param output_file: file_name of output predicted tomograms
        :param model: path to trained network model .h5
        :param gpuID: (0,1,2,3) The gpuID to used during the training. e.g 0,1,2,3.
        :param cube_size: (64) The tomogram is divided into cubes to predict due to the memory limitation of GPUs.
        :param crop_size: (96) The side-length of cubes cropping from tomogram in an overlapping strategy
        :param batch_size: The batch size of the cubes grouped into for network predicting
        :param norm: (True) if normalize the tomograms by percentile
        :param log_level: ("debug") level of message to be displayed
        :raises: AttributeError, KeyError
        """
        from IsoNet.bin.predict import predict
        d = locals()

        d_args = Arg(d)
        predict(d_args)

    def make_mask(self,tomo_path,mask_path: str = None,side: int=8,percentile: int=99,threshold: int=1,mask_type: str="statistical"):
        """
        generate a mask to constrain sampling area of the tomogram
        :param tomo_path: path to the tomogram or tomogram folder
        :param mask_path: path and name of the mask to save as
        :param side: (8) The size of the box from which the max-filter and std-filter are calculated. *side* is suggested to be set close to the size of interested particles
        :param percentile: (99) The approximate percentage, ranging from 0 to 100, of the area of meaningful content in tomograms. 
        :param threshold: (1) A factor of overall standard deviation and its default value is 1. This parameter only affect the std-mask. Make the threshold smaller (larger) when you want to enlarge (shrink) mask area. When you don't want to use the std-mask, set the value to 0.
        :param mask_type: 'statistical' or 'surface': Masks can be generated based on the statistics or just take the middle part of tomograms
        """
        from IsoNet.bin.make_mask import make_mask,make_mask_dir
        if os.path.isdir(tomo_path):
            make_mask_dir(tomo_path,mask_path,side=side,percentile=percentile,threshold=threshold,mask_type=mask_type)
        elif os.path.isfile(tomo_path):
            if mask_path is None:
                mask_path = tomo_path.split('.')[0]+'_mask.mrc'
                print(mask_path)
            make_mask(tomo_path,mask_path,side=side,percentile=percentile,threshold=threshold,mask_type=mask_type)
        else:
            print('make_mask tomo_path error')
        print('mask generated')

    def generate_noise(self,output_folder: str,number_volume: int, cubesize: int, minangle: int=-60,maxangle: int=60,
    anglestep: int=2, start: int=0,ncpus: int=20, mode: int=1):
        """
        Generate training noise to accelerate the missing wedge information retrieval. This commond will generate a folder containing noise volumes which mimics the distorded noise pattern in the tomograms with size of cubesize x cubesize x cubesize. The noise volumes are indexed from start to start + number_volume
        :param output_folder: path to folder for saving noises
        :param number_volume: number of noise cubes to generate
        :param cubesize: side length of the noise cubes, usually 64 or 96
        :param ncpus: (20) number of cpus to use
        :param minangle: (-60) the minimal angle of your tilt series
        :param maxangle: (60) the maximal angle of your tilt series
        :param anglestep: (2) the step of your tilt series' angles
        :param start: (0) When you want to add additional noise volumes, you can specify the start value as the number of already generated noise volumes. So the alreaded generated volumes will not be ovewrited.
        :param mode: (1) mode=1, noise is reconstructed by back-projection algorithm; mode=2 or else, noise is gained by filtering gaussian noise volumes.
        """
        from IsoNet.util.noise_generator import make_noise
        make_noise(output_folder=output_folder, number_volume=number_volume, cubesize=cubesize, minangle=minangle,maxangle=maxangle, anglestep=anglestep, start=start,ncpus=ncpus, mode=mode)

    def check(self):
        from IsoNet.bin.predict import predict
        from IsoNet.bin.refine import run
        print('IsoNet --version 0.9.9 installed')

    def generate_command(self, tomo_dir: str, mask_dir: str=None, ncpu: int=10, gpu_memory: int=10, ngpu: int=4, pixel_size: float=10, also_denoise: bool=True):
        """
        \nGenerate recommanded parameters for "isonet.py refine" for users\n
        Only print command, not run it.
        :param input_dir: (None) directory containing tomogram(s) from which subtomos are extracted; format: .mrc or .rec
        :param mask_dir: (None) folder containing mask files, Eash mask file corresponds to one tomogram file, usually basename-mask.mrc
        :param ncpu: (10) number of avaliable cpu cores
        :param ngpu: (4) number of avaliable gpu cards
        :param gpu_memory: (10) memory of each gpu
        :param pixel_size: (10) pixel size in anstroms
        :param: also_denoise: (True) Preform denoising after 15 iterations when set true
        """
        import mrcfile
        import numpy as np
        s="isonet.py refine --input_dir {} ".format(tomo_dir)
        if mask_dir is not None:
            s+="--mask_dir {} ".format(mask_dir)
            m=os.listdir(mask_dir)
            with mrcfile.open(mask_dir+"/"+m[0]) as mrcData:
                mask_data = mrcData.data
            # vsize=np.count_nonzero(mask_data)
        else:
            m=os.listdir(tomo_dir)
            with mrcfile.open(tomo_dir+"/"+m[0]) as mrcData:
                tomo_data = mrcData.data
            sh=tomo_data.shape
            mask_data = np.ones(sh)
        num_tomo = len(m)

        s+="--preprocessing_ncpus {} ".format(ncpu)
        s+="--gpuID "
        for i in range(ngpu-1):
            s+=str(i)
            s+=","
        s+=str(ngpu-1)
        s+=" "
        if pixel_size < 15.0:
            filter_base = 64
            s+="--filter_base 64 "
        else:
            filter_base = 32
            s+="--filter_base 32"
#        if ngpu < 6:
#            batch_size = 2 * ngpu
#            s+="--batch_size {} ".format(batch_size)
        # elif ngpu == 3:
        #     batch_size = 6
        #     s+="--batch_size 6 "
 #       else:
        batch_size = (int(ngpu/7.0)+1) * ngpu
        s+="--batch_size {} ".format(ngpu)
        if filter_base==64:
            cube_size = int((gpu_memory/(batch_size/ngpu)) ** (1/3.0) *40 /16)*16
        elif filter_base ==32:
            cube_size = int((gpu_memory*3/(batch_size/ngpu)) ** (1/3.0) *40 /16)*16

        if cube_size == 0:
            print("Please use larger memory GPU or use more GPUs")

        s+="--cube_size {} --crop_size {} ".format(cube_size, int(cube_size*1.5))

        # num_per_tomo = int(vsize/(cube_size**3) * 0.5)
        num_per_tomo = len(mask_mesh_seeds(mask_data,cube_size)[0] )
        s+="--ncube {} ".format(num_per_tomo)

        num_particles = int(num_per_tomo * num_tomo * 16 * 0.9)
        s+="--epochs 10 --steps_per_epoch {} ".format(int(num_particles/batch_size*0.4))

        if also_denoise:
            s+="--iterations 40 --noise_level 0.05 --noise_start_iter 15 --noise_pause 3"
        else:
            s+="--iterations 15 --noise_level 0 --noise_start_iter 100"
        print(s)

    def deconv(self,tomo, defocus: float=1.0, pixel_size: float=1.0,snrfalloff: float=1.0, deconvstrength: float=1.0):
        """
        \nCTF deconvolutin with weiner filter\n
        :param tomo: tomogram file
        :param defocus: (1) defocus in um
        :param pixel_size: (10) pixel size in anstroms
        :param: snrfalloff: (1.0) The larger this values, more high frequency informetion are filtered out. 
        :param deconvstrength: (1.0) 
        """
        import mrcfile
        with mrcfile.open(tomo) as mrc:
            vol = mrc.data
        result = tom_deconv_tomo(vol, angpix=pixel_size, defocus=defocus, snrfalloff=snrfalloff, deconvstrength=deconvstrength, highpassnyquist=0.1, phaseflipped=False, phaseshift=0 )
        outname = tomo.split('.')[0] +'-deconv.rec'
        with mrcfile.new(outname, overwrite=True) as mrc:
            mrc.set_data(result)

    def extract(self,
        input_dir: str = None,
        mask_dir: str= None,
        crop_size: int = 96,
        ncube: int = 1,
        ):
        """
        \nExtract subtomograms\n
        :param input_dir: (None) directory containing tomogram(s) from which subtomos are extracted; format: .mrc or .rec
        :param mask_dir: (None) folder containing mask files, Eash mask file corresponds to one tomogram file, usually basename-mask.mrc
        :param crop_size: (96) Size of cubes to impose missing wedge. Should be same or larger than size of cubes. Recommend 1.5 times of cube size
        :param ncube: (1) Number of cubes generated for each tomogram. Because each sampled subtomogram rotates 16 times, the actual number of subtomograms for trainings is ncube*16.
        """
        from IsoNet.preprocessing.prepare import extract_subtomos
        d = locals()
        d_args = Arg(d)
        d_args.only_extract_subtomos = True
        extract_subtomos(d_args)

def Display(lines, out):
    text = "\n".join(lines) + "\n"
    out.write(text)

if __name__ == "__main__":
    core.Display = Display
    fire.Fire(ISONET)
