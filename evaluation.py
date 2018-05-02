import tensorflow as tf
import numpy as np
import gpflow
import gpitch
import os
import time
import pickle
import matplotlib.pyplot as plt
import pandas as pd
from scipy.fftpack import fft
from IPython.display import display
from gpitch import window_overlap
import gpitch.myplots as mplt
from gpitch.methods import logistic_tf


def evaluation_notebook(gpu='0', inst=0, nivps=[20, 20], maxiter=[1, 1], learning_rate=[0.0025, 0.0025], 
                        minibatch_size=None, frames=14*16000, start=0, opt_za=True, window_size=8001, 
                        disp=False, overlap=True):
    """
    param nivps: number of inducing variables per second, for activations and components
    """
    
    ## intialization
    if frames < window_size:
        window_size = frames
    sess = gpitch.init_settings(gpu)  # select gpu to use
    nlinfun = gpitch.logistic_tf  # use logistic or gaussian 
    
    ## load pitch models
    directory = '/import/c4dm-04/alvarado/results/ss_amt/train/logistic/'  # location saved models
    linst = ['011PFNOM', '131EGLPM', '311CLNOM', 'ALVARADO']  # list of instruments
    instrument = linst[inst]
    pattern = instrument  # which model version
    m, names_list = gpitch.loadm(directory=directory, pattern=pattern)  
    mplt.plot_trained_models(m, instrument)

    ## load training data
    test_data_dir = '/import/c4dm-04/alvarado/datasets/ss_amt/test_data/'
    lfiles = []
    lfiles += [i for i in os.listdir(test_data_dir) if instrument + '_mixture' in i]
    xall, yall, fs = gpitch.readaudio(test_data_dir + lfiles[0], aug=False, start=start, frames=frames)
    yall2 = np.vstack((  yall.copy(), 0.  )) 
    xall2 = np.vstack((  xall.copy(), xall[-1].copy() + xall[1].copy()  ))
    if overlap:
        x, y = window_overlap.windowed(xall2.copy(), yall2.copy(), ws=window_size)  # return list of segments
    else:
        x, y = gpitch.segment(xall2.copy(), yall2.copy(), window_size=window_size, aug=False)  # return list of segments    
    results_list = len(x)*[None]
    
    ## optimize by windows
    for i in range(len(y)):
        
        if i == 0: 
            ## initialize model (do this only once)
            z = gpitch.init_iv(x=x[i], num_sources=3, nivps_a=nivps[0], nivps_c=nivps[1], fs=fs)  # define location inducing variables
            kern = gpitch.init_kernel_with_trained_models(m)
            mpd = gpitch.pdgp.Pdgp(x[i].copy(), y[i].copy(), z, kern, minibatch_size=minibatch_size, nlinfun=nlinfun)
            mpd.za.fixed = True
            mpd.zc.fixed = True
        else:
             ## reset model to analyze a new window
            gpitch.reset_model(m=mpd, x=x[i].copy(), y=y[i].copy(), nivps=nivps) 

        ## plot training data (windowed)    
        plt.figure(5), plt.title("Test data  " + lfiles[0])
        plt.plot(mpd.x.value, mpd.y.value)
        
        ## optimization
        st = time.time() 
        if minibatch_size is None:
            print ("Optimizing using VI")
            mpd.optimize(disp=True, maxiter=maxiter[0])
        else:
            print ("Optimizing using SVI")
            mpd.optimize(method=tf.train.AdamOptimizer(learning_rate=learning_rate[0], epsilon=0.1), maxiter=maxiter[0])
        print("Time {} secs".format(time.time() - st))
        
        ## optimization location inducing variables
        if opt_za: 
            mpd.za.fixed = False
            st = time.time()
            if minibatch_size is None:
                print ("Optimizing location inducing variables using VI")
                mpd.optimize(disp=True, maxiter=maxiter[1])
            else:
                print ("Optimizing location inducing variables using SVI")
                mpd.optimize(method=tf.train.AdamOptimizer(learning_rate=learning_rate[1], epsilon=0.1), maxiter=maxiter[1])
            print("Time {} secs".format(time.time() - st))
            mpd.za.fixed = True
    
        ## prediction
        results_list[i] = mpd.predict_act_n_com(x[i].copy())
        
        ## plot results
        mplt.plot_sources_all(x[i], y[i], results_list[i][4])
        tf.reset_default_graph()
    
    return mpd, results_list


#         q_mu_acts_l[0].append(mpd.q_mu2.value.copy())
#         q_mu_acts_l[1].append(mpd.q_mu4.value.copy())
#         q_mu_acts_l[2].append(mpd.q_mu6.value.copy())

#         q_mu_comps_l[0].append(mpd.q_mu1.value.copy())
#         q_mu_comps_l[1].append(mpd.q_mu3.value.copy())
#         q_mu_comps_l[2].append(mpd.q_mu5.value.copy())

#         q_sqrt_acts_l[0].append(mpd.q_sqrt2.value.copy())
#         q_sqrt_acts_l[1].append(mpd.q_sqrt4.value.copy())
#         q_sqrt_acts_l[2].append(mpd.q_sqrt6.value.copy())

#         q_sqrt_comps_l[0].append(mpd.q_sqrt1.value.copy())
#         q_sqrt_comps_l[1].append(mpd.q_sqrt3.value.copy())
#         q_sqrt_comps_l[2].append(mpd.q_sqrt5.value.copy())

#         

#         if disp:

#             print("Likelihood")
#             display(mpd.likelihood)

#             print("Activation kernels")
#             display(mpd.kern_g1)
#             display(mpd.kern_g2)
#             display(mpd.kern_g3)

#             print("Component kernels")
#             data_com_kern = pd.DataFrame({'Lengthscales':[mpd.kern_f1.lengthscales.value[0].copy(),
#                                                           mpd.kern_f2.lengthscales.value[0].copy(),
#                                                           mpd.kern_f3.lengthscales.value[0].copy()]})
#             display(data_com_kern)

#     results_l = [mf_l, mg_l, vf_l, vg_l, x_l, y_l, q_mu_acts_l, q_mu_comps_l, q_sqrt_acts_l, q_sqrt_comps_l]


#     #rm = window_overlap.merge_all(results_l)  # results merged
#     #s1_l, s2_l, s3_l = window_overlap.append_sources(rm)  # get patches of sources
#     #window_overlap.plot_patches(rm, s1_l, s2_l, s3_l)
#     #x, y, s = window_overlap.get_results_arrays(sl=[s1_l, s2_l, s3_l], rm=rm, ws=window_size)
#     #window_overlap.plot_sources(x, y, s)
#     #final_results = [x, y, s]

#     #return all_models_list, final_results
    
#     # import soundfile
#     # import numpy as np
#     # pitch = ['E', 'C', 'G']
#     # for i in range(3):
#     #     name = "011PFNOM_" + pitch[i] + "_part.wav"
#     #     soundfile.write(name, rl[2][i]/np.max(np.abs(rl[2][i])), 16000)
# #
