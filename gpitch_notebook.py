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


def plot_results(mean_f, var_f, mean_g, var_g, x_plot, y, za, zc, xlim):

    mean_act = gpitch.gaussfunc(mean_g)
    plt.figure()
    plt.subplot(1, 4, 1), plt.title('data')
    plt.plot(x_plot, y)
    # plt.plot(z, -np.ones(z.shape), 'k|', mew=1)
    plt.xlim(xlim)

    plt.subplot(1, 4, 2), plt.title('data approx')
    plt.plot(x_plot, mean_act * mean_f, lw=2)
    # plt.plot(z, -np.ones(z.shape), 'k|', mew=1)
    plt.xlim(xlim)

    plt.subplot(1, 4, 3), plt.title('activation')
    plt.plot(x_plot, mean_act, 'C0', lw=2)
    plt.fill_between(x_plot, gpitch.gaussfunc(mean_g-2*np.sqrt(var_g)), gpitch.gaussfunc(mean_g+2*np.sqrt(var_g)), color='C0',
                     alpha=0.2)
    plt.plot(za, np.zeros(za.shape), 'k|', mew=1)
    plt.xlim(xlim)

    plt.subplot(1, 4, 4), plt.title('component')
    plt.plot(x_plot, mean_f, 'C0', lw=2)
    plt.fill_between(x_plot, mean_f - 2 * np.sqrt(var_f), mean_f + 2 * np.sqrt(var_f), color='C0', alpha=0.2)
    plt.plot(zc, np.zeros(zc.shape), 'k|', mew=1)
    plt.xlim(xlim)


def plot_loaded_models(m, instr_name):
    for i in range(len(m)):
        x = m[i].x.value.copy()
        y = m[i].y.value.copy()
        za = m[i].za.value.copy()
        zc = m[i].zc.value.copy()
        xplot = x.reshape(-1, ).copy()
        mean_g, var_g = m[i].prediction_act
        mean_f, var_f = m[i].prediction_com
        plot_results(mean_f.reshape(-1,), var_f.reshape(-1,), mean_g.reshape(-1,), var_g.reshape(-1,), xplot, y, za, zc,
                     xlim=[-0.01, 1.01])
        plt.suptitle(instr_name)


def re_init_params(m, x, y, nivps):

    # reset inducing variables
    dec_a = 16000/nivps[0]
    dec_c = 16000/nivps[1]
    za1 = np.vstack([x[::dec_a].copy(), x[-1].copy()])  # location inducing variables
    zc1 = np.vstack([x[::dec_c].copy(), x[-1].copy()])  # location inducing variables
    za2 = 0.33*(za1[1] - za1[0]) + np.vstack([x[::dec_a].copy(), x[-1].copy()])  # location inducing variables
    zc2 = 0.33*(zc1[1] - zc1[0]) + np.vstack([x[::dec_c].copy(), x[-1].copy()])  # location inducing variables
    za3 = 0.66*(za1[1] - za1[0]) + np.vstack([x[::dec_a].copy(), x[-1].copy()])  # location inducing variables
    zc3 = 0.66*(zc1[1] - zc1[0]) + np.vstack([x[::dec_c].copy(), x[-1].copy()])  # location inducing variables

    m.Za1 = za1.copy()
    m.Za2 = za2.copy()
    m.Za3 = za3.copy()
    m.Zc1 = zc1.copy()
    m.Zc2 = zc2.copy()
    m.Zc3 = zc3.copy()

    # reset input data
    m.X = x.copy()
    m.Y = y.copy()

    # reset variational parameters
    m.q_mu1 = np.zeros((zc1.shape[0], 1))  # f1
    m.q_mu2 = np.zeros((za1.shape[0], 1))  # g1
    m.q_mu3 = np.zeros((zc2.shape[0], 1))  # f2
    m.q_mu4 = np.zeros((za2.shape[0], 1))  # g2
    m.q_mu5 = np.zeros((zc3.shape[0], 1))  # f3
    m.q_mu6 = np.zeros((za3.shape[0], 1))  # g3

    q_sqrt_a1 = np.array([np.eye(za1.shape[0]) for _ in range(1)]).swapaxes(0, 2)
    q_sqrt_c1 = np.array([np.eye(zc1.shape[0]) for _ in range(1)]).swapaxes(0, 2)
    q_sqrt_a2 = np.array([np.eye(za2.shape[0]) for _ in range(1)]).swapaxes(0, 2)
    q_sqrt_c2 = np.array([np.eye(zc2.shape[0]) for _ in range(1)]).swapaxes(0, 2)
    q_sqrt_a3 = np.array([np.eye(za3.shape[0]) for _ in range(1)]).swapaxes(0, 2)
    q_sqrt_c3 = np.array([np.eye(zc3.shape[0]) for _ in range(1)]).swapaxes(0, 2)

    m.q_sqrt1 = q_sqrt_c1.copy()
    m.q_sqrt2 = q_sqrt_a1.copy()
    m.q_sqrt3 = q_sqrt_c2.copy()
    m.q_sqrt4 = q_sqrt_a2.copy()
    m.q_sqrt5 = q_sqrt_c3.copy()
    m.q_sqrt6 = q_sqrt_a3.copy()

    # reset hyper-parameters
    m.kern_g1.variance = 4.
    m.kern_g2.variance = 4.
    m.kern_g3.variance = 4.

    m.kern_g1.lengthscales = 0.5
    m.kern_g2.lengthscales = 0.5
    m.kern_g3.lengthscales = 0.5

    m.kern_f1.lengthscales = 1.0
    m.kern_f2.lengthscales = 1.0
    m.kern_f3.lengthscales = 1.0

    m.likelihood.variance = 1.


def get_lists_save_results():
    return [], [], [], [], [], [], [[], [], []], [[], [], []], [[], [], []], [[], [], []]


def test_notebook(gpu='0', inst=0, nivps=[1000, 1000], maxiter=[500, 20], learning_rate=[0.0025, 0.0025], minibatch_size=None,
                         frames=4000, start=0, opt_za=False, window_size=2001, disp=False, varfix=False, overlap=True):
    """
    param nivps: number of inducing variables per second, for activations and components
    """

    if frames < window_size:
        window_size = frames

    sess = gpitch.init_settings(gpu)  # select gpu to use

    linst = ['011PFNOM', '131EGLPM', '311CLNOM', 'ALVARADO']  # list of instruments
    instrument = linst[inst]
    directory = '/import/c4dm-04/alvarado/results/ss_amt/train/'  # location saved models
    directory = '/home/pa/Desktop/ss_amt/results/logistic/'
    pattern = 'trained_25_modgp2_new_var_1' + instrument  # which model version

    m, names_list = gpitch.loadm(directory=directory, pattern=pattern)  # load pitch models
    #plot_loaded_models(m, instrument)

    # load data
    test_data_dir = '/import/c4dm-04/alvarado/datasets/ss_amt/test_data/'
    test_data_dir = '/home/pa/Desktop/ss_amt/test_data/'
    lfiles = []
    lfiles += [i for i in os.listdir(test_data_dir) if instrument + '_mixture' in i]

    xall, yall, fs = gpitch.readaudio(test_data_dir + lfiles[0], aug=False, start=start, frames=frames)

    yall2 = np.vstack((  yall.copy(), 0.  ))
    xall2 = np.vstack((  xall.copy(), xall[-1].copy() + xall[1].copy()  ))

    if overlap:
        x, y = window_overlap.windowed(xall2.copy(), yall2.copy(), ws=window_size)  # return list of segments
    else:
        x, y = gpitch.segment(xall2.copy(), yall2.copy(), window_size=window_size, aug=False)  # return list of segments

    nlinfun = gpitch.logistic_tf  # use logistic or gaussian as non-linear transform for activations
    mpd = gpitch.pdgp.init_model(x=x[0].copy(), y=y[0].copy(), m1=m[0], m2=m[1], m3=m[2], niv_a=nivps[0], niv_c=nivps[1],
                                 minibatch_size=minibatch_size, nlinfun=nlinfun, quad=True, varfix=varfix)  # init pitch detec model

    mf_l, mg_l, vf_l, vg_l, x_l, y_l, q_mu_acts_l, q_mu_comps_l, q_sqrt_acts_l, q_sqrt_comps_l = get_lists_save_results()

    for i in range(len(y)):

        if i is not 0:
            re_init_params(m=mpd, x=x[i].copy(), y=y[i].copy(), nivps=nivps)

        plt.figure(5), plt.title("Test data  " + lfiles[0])
        plt.plot(x[i], y[i])

        # st = time.time()  # run optimization

        if minibatch_size is None:
            print ("Optimizing using VI")
            mpd.optimize(disp=True, maxiter=maxiter[0])
        else:
            print ("Optimizing using SVI")
            mpd.optimize(method=tf.train.AdamOptimizer(learning_rate=learning_rate[0], epsilon=0.1), maxiter=maxiter[0])

        # print("Time {} secs".format(time.time() - st))

        if opt_za: # if True, optimize location inducing variables of activations
            mpd.Za1.fixed = False
            mpd.Za2.fixed = False
            mpd.Za3.fixed = False

            # st = time.time()

            if minibatch_size is None:
                print ("Optimizing location inducing variables using VI")
                mpd.optimize(disp=True, maxiter=maxiter[1])
            else:
                print ("Optimizing location inducing variables using SVI")
                mpd.optimize(method=tf.train.AdamOptimizer(learning_rate=learning_rate[1], epsilon=0.1), maxiter=maxiter[1])

            # print("Time {} secs".format(time.time() - st))

            mpd.Za1.fixed = True
            mpd.Za2.fixed = True
            mpd.Za3.fixed = True

        mf, vf, mg, vg, x_plot, y_plot =  gpitch.ssgp.predict_windowed(x=x[i], y=y[i], predfunc=mpd.predictall, nw=window_size)  # predict
        gpitch.myplots.plot_ssgp(mpd, mean_f=mf, var_f=vf, mean_g=mg, var_g=vg, x_plot=x_plot, y=y_plot)  # plot results


        mf_l.append(list(mf))
        mg_l.append(list(mg))
        vf_l.append(list(vf))
        vg_l.append(list(vg))
        x_l.append(x_plot)
        y_l.append(y_plot)

        q_mu_acts_l[0].append(mpd.q_mu2.value.copy())
        q_mu_acts_l[1].append(mpd.q_mu4.value.copy())
        q_mu_acts_l[2].append(mpd.q_mu6.value.copy())

        q_mu_comps_l[0].append(mpd.q_mu1.value.copy())
        q_mu_comps_l[1].append(mpd.q_mu3.value.copy())
        q_mu_comps_l[2].append(mpd.q_mu5.value.copy())

        q_sqrt_acts_l[0].append(mpd.q_sqrt2.value.copy())
        q_sqrt_acts_l[1].append(mpd.q_sqrt4.value.copy())
        q_sqrt_acts_l[2].append(mpd.q_sqrt6.value.copy())

        q_sqrt_comps_l[0].append(mpd.q_sqrt1.value.copy())
        q_sqrt_comps_l[1].append(mpd.q_sqrt3.value.copy())
        q_sqrt_comps_l[2].append(mpd.q_sqrt5.value.copy())

        tf.reset_default_graph()

        if disp:

            print("Likelihood")
            display(mpd.likelihood)

            print("Activation kernels")
            display(mpd.kern_g1)
            display(mpd.kern_g2)
            display(mpd.kern_g3)

            print("Component kernels")
            data_com_kern = pd.DataFrame({'Lengthscales':[mpd.kern_f1.lengthscales.value[0].copy(),
                                                          mpd.kern_f2.lengthscales.value[0].copy(),
                                                          mpd.kern_f3.lengthscales.value[0].copy()]})
            display(data_com_kern)

    results_l = [mf_l, mg_l, vf_l, vg_l, x_l, y_l, q_mu_acts_l, q_mu_comps_l, q_sqrt_acts_l, q_sqrt_comps_l]


    #rm = window_overlap.merge_all(results_l)  # results merged
    #s1_l, s2_l, s3_l = window_overlap.append_sources(rm)  # get patches of sources
    #window_overlap.plot_patches(rm, s1_l, s2_l, s3_l)
    #x, y, s = window_overlap.get_results_arrays(sl=[s1_l, s2_l, s3_l], rm=rm, ws=window_size)
    #window_overlap.plot_sources(x, y, s)
    #final_results = [x, y, s]

    #return all_models_list, final_results


def train_notebook(gpu='0', list_limits=[0,-1], maxiter=[1, 2], nivps=[20, 20], frames=2000):
    sess = gpitch.init_settings(gpu)  # choose gpu to work
    plt.rcParams['figure.figsize'] = (16, 4)  # set plot size

    # import 12 audio files for intializing component parameters
    #_______________________________________________________________________________________________
    datadir = '/import/c4dm-04/alvarado/datasets/ss_amt/training_data/'
    datadir = '/home/pa/Desktop/ss_amt/training_data/'
    lfiles = gpitch.lfiles_training
    lfiles = lfiles[list_limits[0]:list_limits[1]]
    numf = len(lfiles)  # number of files loaded
    if0 = gpitch.find_ideal_f0(lfiles)  # ideal frequency for each pitch

    x2, y2, fs2 = [], [], []
    for i in range(numf):
        a, b, c = gpitch.readaudio(datadir + lfiles[i], frames=32000, aug=False)
        x2.append(a.copy())
        y2.append(b.copy())
        fs2.append(c)

    # plt.figure(figsize=(16, 12))  # visualize loaded data
    # for i in range(numf):
    #     plt.subplot(4, 3, i+1)
    #     plt.plot(x2[i], y2[i])
    #     plt.suptitle('Training data')

    lkernel, iparam = gpitch.init_kernel_training(y=y2, list_files=lfiles)

    # Compare FFT kernels and initialization data
    #_______________________________________________________________________________________________
    array0 = np.asarray(0.).reshape(-1,1)
    x_p = np.linspace(-4, 4, 8*16000).reshape(-1, 1)

    k_p = []
    for i in range(numf):
        k_p.append(lkernel[1][i].compute_K(x_p, array0))

    Fdata = np.linspace(0., 8000., 16000).reshape(-1, 1)
    Fkernel = np.linspace(0., 8000., 4*16000).reshape(-1, 1)

    gpitch.pltrain.plot_fft(Fdata, Fkernel, y2, k_p, numf, iparam)


    # import 12 audio files for training (same data but only 0.5 seconds)
    #_______________________________________________________________________________________________
    n = frames
    x, y, fs = [], [], []
    for i in range(numf):
        a, b, c = gpitch.readaudio(datadir + lfiles[i], frames=n, aug=False)
        x.append(a.copy())
        y.append(b.copy())
        fs.append(c)

    # plt.figure(figsize=(16, 12))  # visualize loaded data
    # for i in range(numf):
    #     plt.subplot(4, 3, i+1)
    #     plt.plot(x[i], y[i])

    # initialize models
    #_______________________________________________________________________________________________
    m = []
    nivps_a, nivps_c = nivps[0], nivps[1]  # num inducing variables per second for act and comp
    nlinfun = gpitch.logistic
    for i in range(numf):
        z = gpitch.init_iv(x=x[i], num_sources=numf, nivps_a=nivps_a, nivps_c=nivps_c, fs=fs[i])
        kern = [ [lkernel[0][i]], [lkernel[1][i]] ]
        m.append(gpitch.pdgp.Pdgp(x=x[i], y=y[i], z=z, kern=kern))
        m[i].za.fixed = True
        m[i].zc.fixed = True

    # optimization
    #_______________________________________________________________________________________________
    for i in range(numf):
        st = time.time()
        m[i].kern_act[0].variance.fixed = True
        m[i].optimize(disp=1, maxiter=maxiter[0])
        m[i].za.fixed = False
        m[i].optimize(disp=1, maxiter=maxiter[1])
        print("model {}, time optimizing {} sec".format(i+1, time.time() - st))
        tf.reset_default_graph()

    # prediction
    #_______________________________________________________________________________________________
    m_a, v_a = [], []  # list mean, var activation
    m_c, v_c = [], []  # list mean, var component
    m_s = []  # mean source

    for i in range(numf):
        st = time.time()
        mean_act, var_act = m[i].predict_act(x[i])
        mean_com, var_com = m[i].predict_com(x[i])
        print("model {}, time predicting {}".format(str(i + 1), time.time() - st) )
        m_s.append(gpitch.logistic(mean_act[0])*mean_com[0])
        m_a.append(mean_act[0])
        m_c.append(mean_com[0])
        v_a.append(var_act[0])
        v_c.append(var_com[0])
        tf.reset_default_graph()


    gpitch.pltrain.plot_prediction(x=x, y=y, source=m_s, m_a=m_a, v_a=v_a, m_c=m_c, v_c=v_c, m=m, nlinfun=nlinfun)

    gpitch.pltrain.plot_parameters(m)

    k_p2 = []
    for i in range(numf):
        k_p2.append(m[i].kern_com[0].compute_K(x_p, array0))

    gpitch.pltrain.plot_fft(Fdata, Fkernel, y2, k_p2, numf, iparam)


    for i in range(numf):
        m[i].prediction_act = [m_a[i], v_a[i]]
        m[i].prediction_com = [m_c[i], v_c[i]]
        location = "/home/pa/Desktop/ss_amt/results/logistic/" +  lfiles[i].strip('.wav')+".p"
        # location = "/import/c4dm-04/alvarado/results/ss_amt/train/trained_25_modgp2_new_var_1" +  lfiles[i].strip('.wav')+".p"
        pickle.dump(m[i], open(location, "wb"))

    return m




#
