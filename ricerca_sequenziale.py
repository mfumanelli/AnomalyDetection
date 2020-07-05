import numpy as np
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.neighbors import KDTree
from mpmath import (
    sqrt,
    pi,
    atan,
    hyp2f1,
    gamma,
    erfinv,
    power,
)
import time
from sklearn.decomposition import PCA
import random

plt.style.use("ggplot")


def creazione_df(nobs, nvar, dim_segnale, sigmas, flat_frac):
    sigma = np.random.uniform(sigmas[0], sigmas[1], dim_segnale)
    mean = np.random.uniform(3 * sigma, 1 - (3 * sigma))
    gauss_indices = random.sample(range(1, nvar), dim_segnale)

    columns = list(np.arange(nvar))

    df = pd.DataFrame(np.random.uniform(0, 1, size=(nobs, nvar)), columns=columns)
    df.insert(0, "Signal", np.zeros(nobs), True)
    for i in np.arange(0, nobs):
        tmp = 0
        if i < flat_frac * nobs:
            df.iloc[i, 0] = 0
        else:
            for p in gauss_indices:
                df.iloc[i, p] = np.random.normal(mean[tmp], sigma[tmp])
                df.iloc[i, 0] = 1
                tmp += 1
    df = df.sample(frac=1).reset_index(drop=True)

    return df


def ecdf(x_i, npoints):
    """Generates an Empirical CDF using the indicator function.

    Inputs:
    x_i -- the input data set, should be a numpy array
    npoints -- the number of desired points in the empirical CDF estimate

    Outputs:
    y -- the empirical CDF
    """
    # define the points over which we will generate the kernel density estimate
    x = np.linspace(min(x_i), max(x_i), npoints)
    n = float(x_i.size)
    y = np.zeros(npoints)

    for ii in np.arange(x.size):
        idxs = np.where(x_i <= x[ii])
        y[ii] = np.sum(idxs[0].size) / n

    return (x, y)


def kde_integral(kde):
    """Generates a "smoother" Empirical CDF by integrating the KDE.  For this,
        the user should first generate the KDE using kde.py, and then pass the
        density estimate to this function

        Inputs:
        kde -- the kernel density estimate

        Outputs:
        y -- the smoothed CDF estimate
    """
    y = np.cumsum(kde) / sum(kde)

    return y


def probability_integral_transform(X):
    """
    Takes a data array X of dimension [M x N], and converts it to a uniform
    random variable using the probability integral transform, U = F(X)
    """
    M = X.shape[0]
    N = X.shape[1]

    # convert X to U by using the probability integral transform:  F(X) = U
    U = np.empty(X.shape)
    for ii in range(0, N):
        x_ii = X[:, ii]

        # estimate the empirical cdf
        (xx, pp) = ecdf(x_ii, M)
        f = interp1d(xx, pp)  # TODO: experiment w/ different kinds of interpolation?
        # for example, cubic, or spline etc...?

        # plug this RV sample into the empirical cdf to get uniform RV
        u_ii = f(x_ii)
        U[:, ii] = u_ii

    return U


def random_box_subspace(NVar, NRanBox, eps=0.01):
    bmin = eps * (np.random.uniform(size=NVar) / eps).astype(np.int32)
    bmax = eps * (np.random.uniform(size=NVar) / eps).astype(np.int32)
    is_random = np.random.uniform(size=NVar) < (NRanBox / NVar)
    bmin = bmin * is_random
    bmax = bmax * is_random + ~is_random
    Blockmin = np.min([bmin, bmax], axis=0)
    Blockmax = np.max([bmin, bmax], axis=0)
    VolumeOrig = np.cumprod(Blockmax - Blockmin)
    # first_idx_not_valid = np.argmax((VolumeOrig * goodevents) < 1)
    first_idx_not_valid = np.argmax(VolumeOrig < 0.001)
    Blockmin[(first_idx_not_valid - 1) :] = 0
    Blockmax[(first_idx_not_valid - 1) :] = 1
    if first_idx_not_valid == 0:
        return random_box_subspace(NVar, NRanBox)
    return Blockmin, Blockmax, VolumeOrig[first_idx_not_valid - 1]


# In[12]:


def get_included_points_indices_subspace(min_lims, max_lims, subspace_indices, X):
    index = np.arange(len(X))
    for k in range(len(subspace_indices)):
        var_k = X[index, :][:, subspace_indices[k]]
        index = index[(var_k <= max_lims[k]) & (var_k >= min_lims[k])]

    return index


# In[13]:


def sidebands(subspace_indices, Blockmin, Blockmax):
    sidewidth = 0.5 * (2 ** (1 / len(subspace_indices)) - 1)
    Sidemin = Blockmin + sidewidth * (Blockmin - Blockmax)
    Sidemax = Blockmax + sidewidth * (Blockmax - Blockmin)
    Sidemin = np.maximum(np.zeros_like(Sidemin), Sidemin)
    Sidemax = np.minimum(np.ones_like(Sidemax), Sidemax)
    return Sidemin, Sidemax


# In[14]:


def ZPLtau(Non, Noff, tau):
    if Non == 0 or Noff == 0:
        return 0
    else:
        Ntot = Non + Noff
        z = np.sqrt(2.0) * np.sqrt(
            Non * np.log(Non * (1 + tau) / (Ntot))
            + Noff * np.log(Noff * (1 + tau) / (Ntot * tau))
        )
        if Non < (Noff / (tau)):
            return -z
        else:
            return z


# In[15]:


def PCA_f(X, soglia):
    pca = PCA(n_components=len(X.columns))  # max number of pca
    pca.fit(X)
    X_transformed = pca.transform(X)
    var_cumulata = np.array(
        [pca.explained_variance_ratio_[:i].sum() for i in range(1, len(X.columns))]
    ).round(2)
    idx_ok = np.argmax(var_cumulata >= soglia)
    pca_names = []
    for i in range(idx_ok):
        tmp = ["PCA", str(i + 1)]
        pca_names.append(" ".join(tmp))
    X_df_transformed = pd.DataFrame(
        data=X_transformed[:, :idx_ok], index=None, columns=pca_names
    )
    return X_df_transformed


def get_num_events(block_min, block_max, X):
    return (
        (np.min(X - block_min, axis=1) > 0) & (np.min(block_max - X, axis=1) > 0)
    ).sum()


# In[16]:


def percentuale_segnale(prova):
    size = len(prova)
    ris = np.zeros([size, 2])
    for k, v in prova.items():
        ris[k] = (k, v["box_ZPLtau"])
    punto_max = np.argmax(ris, axis=0)[1]
    sotto_df = df.loc[prova[punto_max]["included_points"], :]
    return len(sotto_df[sotto_df["Signal"] == 1.0]) / len(sotto_df)


# In[17]:


def best_box(dict_scatole, df_completo, frazione_segnale_tot):
    size = len(dict_scatole)
    ris = np.zeros([size, 2])
    for k, v in dict_scatole.items():
        ris[k] = (k, v["box_ZPLtau"])
    punto_max = np.argmax(ris, axis=0)[1]
    sotto_df = df_completo.loc[dict_scatole[punto_max]["included_points"], :]
    out = {
        "scatola_migliore": dict_scatole[punto_max],
        "percentuale_segnale": len(sotto_df[sotto_df["Signal"] == 1.0]) / len(sotto_df),
        "percentuale_segnale_totale": (
            len(sotto_df[sotto_df["Signal"] == 1.0])
            / (len(df_completo) * frazione_segnale_tot)
        ),
    }
    return out


# In[18]:


def ZPL2(Non, Ntot, vol):
    if Non == 0:
        return 0
    else:
        tau = (1 - vol) / ((vol))
        Noff = Ntot - Non
        valore = (Non * np.log(Non * (1 + tau) / Ntot)) + (
            Noff * np.log(Noff * (1 + tau) / (Ntot * tau))
        )
        if valore <= 0:
            z = 0
        else:
            z = np.sqrt(2) * np.sqrt(valore)
        # print(tau)
        if Non < (Noff / tau):
            return -z
        else:
            return z


# In[19]:


def R(Non, Ntot, volume):
    if volume == 0:
        return 0
    else:
        return Non / (Ntot * volume + 1)


# In[20]:


def R2(Non, Noff):
    r = Non / (5 + Noff)
    return r


# In[21]:


def scatola_iniziale_dist_euclidea(X_smpl, leaf_size):
    kdt = KDTree(X_smpl, leaf_size=leaf_size, metric="euclidean")
    p = kdt.query(X_smpl, k=X_smpl.shape[0], return_distance=True)
    a = p[0]
    pr = a == a.min(0)
    pr_somma = pr.astype(int).sum(1)
    pto_centrale = X_smpl[pr_somma.argmax()].copy()
    inf_unif = pto_centrale - 0.1
    sup_unif = pto_centrale + 0.1
    inf_unif[inf_unif < 0] = 0
    sup_unif[sup_unif > 1] = 1
    Blockmin = inf_unif
    Blockmax = sup_unif
    VolumeOrig = np.cumprod(Blockmax - Blockmin)
    # print(VolumeOrig)
    if any(VolumeOrig < 0.001):
        first_idx_not_valid = int(np.where(VolumeOrig < 0.001)[0][0])
        Blockmin[
            (first_idx_not_valid - 1) :
        ] = 0  # non sono così sicura di questa parte
        Blockmax[(first_idx_not_valid - 1) :] = 1
        if first_idx_not_valid == 0:
            #    print(first_idx_not_valid)
            return scatola_iniziale_dist_euclidea(X_smpl, leaf_size)
        return Blockmin, Blockmax, VolumeOrig[first_idx_not_valid - 1]
    else:
        return Blockmin, Blockmax, VolumeOrig[len(Blockmin) - 1]


# In[22]:


def ZPL_bayesiana(Non, Noff, vol):
    alpha = (1 - vol) / (vol)

    def B_01(Non, Noff, alpha):
        Ntot = Non + Noff
        gam = (1 + 2 * Noff) * power(alpha, (0.5 + Ntot)) * gamma(0.5 + Ntot)
        delta = (
            (2 * power((1 + alpha), Ntot))
            * gamma(1 + Ntot)
            * hyp2f1(0.5 + Noff, 1 + Ntot, 1.5 + Noff, (-1 / alpha))
        )
        c1_c2 = sqrt(pi) / (2 * atan(1 / sqrt(alpha)))
        return gam / (c1_c2 * delta)

    buf = 1 - B_01(Non, Noff, alpha)
    if buf < -1.0:
        buf = -1.0
    # print(buf)
    return sqrt("2") * erfinv(buf)


# Nuovo gd

# In[37]:


def gradient_sequenziale(
    X,
    number_trials,  # da quanti punti distinti parto
    numbers_gd_loops,  # quante volte cerco per una determinata scatola
    PCA_opt=False,
    soglia_pca=0.8,
    step_width_val=0.15,
    max_volume_box=0.05,
    epsilon=0.01,
    ZPLtau_alg_orig=True,
    numero_slices=10,
):
    # np.random.seed(10)
    out = {}
    if PCA_opt:
        X = PCA_f(X, soglia_pca)
    X_numpy = X.to_numpy()
    Numbers_variables = X_numpy.shape[1]
    goodevents = X_numpy.shape[0]
    Number_random_boxes = 6  # int(math.log(10/goodevents)/math.log(1/3))
    if Numbers_variables <= Number_random_boxes:
        Number_random_boxes = Numbers_variables
    passaggio = 0
    for ntrial in range(number_trials):
        print(f"ntrial: {ntrial}")
        # selezione casuale di un sottoinsieme di variabili
        if passaggio == 0:
            subspace_indices = np.random.choice(
                Numbers_variables, size=Number_random_boxes, replace=False
            )
        else:  # uso le tre variabili più promettenti tra quelle già selezionate
            # e le altre le seleziono a caso
            intervalli = np.linspace(start=0, stop=1, num=numero_slices)
            num_eventi_variabile_univariata = np.zeros(
                [len(subspace_indices), numero_slices - 1]
            )
            for kk in range(len(subspace_indices)):
                for k_int in range(len(intervalli) - 1):
                    num_eventi_variabile_univariata[kk, k_int] = get_num_events(
                        intervalli[k_int],
                        intervalli[k_int + 1],
                        X_numpy[:, subspace_indices[kk]].reshape((X_numpy.shape[0], 1)),
                    )
            vettore_max = np.max(num_eventi_variabile_univariata, axis=1)
            indici_ordinati = np.argsort(-1 * vettore_max, axis=0)
            subspace_indices[0:3] = indici_ordinati[0:3]
            var_non_usabili = subspace_indices[0:3]
            tot_var = np.arange(X_numpy.shape[1])
            possibili_indici = np.setxor1d(tot_var, var_non_usabili)
            subspace_indices[3:6] = np.random.choice(
                possibili_indici, size=3, replace=False
            )
        passaggio += 1
        sidewidth = 0.5 * (2 ** (1 / Number_random_boxes) - 1)
        X_numpy_smpl = X_numpy[:, subspace_indices]
        #  inizializzazione della prima scatola
        #  obs_indices = np.random.choice(goodevents, size = 5000, replace = False)
        #  X_tmp = X_numpy_smpl[obs_indices,:]
        Blockmin_numpy, Blockmax_numpy, _ = scatola_iniziale_dist_euclidea(
            X_numpy_smpl, leaf_size=4000
        )
        step_width = np.zeros([len(subspace_indices), 4]) + step_width_val
        num_events_block = get_num_events(Blockmin_numpy, Blockmax_numpy, X_numpy_smpl)
        # controllo se per caso la scatola iniziale ha troppi pochi eventi all'interno,
        # in caso richiamo la funzione
        if num_events_block < 1:
            while num_events_block > 1:
                subspace_indices = np.random.choice(
                    Numbers_variables, size=Number_random_boxes, replace=False
                )
                Blockmin_numpy, Blockmax_numpy, _ = scatola_iniziale_dist_euclidea(
                    X_numpy_smpl, leaf_size=4000
                )
                num_events_block = get_num_events(
                    Blockmin_numpy, Blockmax_numpy, X_numpy_smpl
                )
        stop_rule = np.zeros(len(subspace_indices), dtype=bool)
        for gd in range(numbers_gd_loops):
            digrad = 0
            igrad = -1
            # if gd % 10 == 0:
            #    print(f"gd loop: {gd}")
            VolumeOrig = (Blockmax_numpy - Blockmin_numpy).prod()
            Sidebands_min, Sidebands_max = sidebands(
                subspace_indices, Blockmin_numpy, Blockmax_numpy
            )
            VolumeSidebands = (Sidebands_max - Sidebands_min).prod()
            excessvol_pre_move = 2 * VolumeOrig / VolumeSidebands
            # numero eventi contenuti nella scatola
            num_events_block = get_num_events(
                Blockmin_numpy, Blockmax_numpy, X_numpy_smpl
            )
            # numero eventi solo nelle sidebands
            no_step = np.zeros([len(subspace_indices), 4], dtype=bool)
            if VolumeOrig >= max_volume_box:
                no_step[:, 0] = np.ones(len(subspace_indices), dtype=bool)
                no_step[:, 3] = np.ones(len(subspace_indices), dtype=bool)
            no_step[:, 1] = step_width[:, 1] >= (
                Blockmax_numpy - Blockmin_numpy - epsilon
            )
            no_step[:, 2] = step_width[:, 2] >= (
                Blockmax_numpy - Blockmin_numpy - epsilon
            )
            # inizializzare bmin e bmax
            bmin = np.zeros([len(subspace_indices), 4])
            bmax = np.ones([len(subspace_indices), 4])
            # inizializzo VolumeMod
            VolumeMod = np.ones([len(subspace_indices), 4])
            multiplier = VolumeOrig / (Blockmax_numpy - Blockmin_numpy)
            # Sposto solo gli estremi inferiori delle variabili a sinistra
            # io nostep lo uso qui e non prima di calcolare Z
            bmin[:, 0] = Blockmin_numpy - step_width[:, 0]
            bmax[:, 0] = Blockmax_numpy.copy()
            bmin[bmin[:, 0] < 0, 0] = 0
            VolumeMod[:, 0] = multiplier * np.abs(bmax[:, 0] - bmin[:, 0])

            # Sposto solo gli estremi inferiori delle variabili a destra
            bmin[:, 1] = Blockmin_numpy + step_width[:, 1]
            bmax[:, 1] = Blockmax_numpy.copy()
            bmin[bmin[:, 1] > (bmax[:, 1] - epsilon), 1] = (
                bmax[bmin[:, 1] > (bmax[:, 1] - epsilon), 1] - epsilon
            )
            VolumeMod[:, 1] = multiplier * np.abs(bmax[:, 1] - bmin[:, 1])
            # Sposto solo gli estremi superiori delle variabili a sinistra
            bmax[:, 2] = Blockmax_numpy - step_width[:, 2]
            bmin[:, 2] = Blockmin_numpy.copy()
            bmax[bmax[:, 2] < (bmin[:, 2] + epsilon), 2] = (
                bmin[bmax[:, 2] < (bmin[:, 2] + epsilon), 2] + epsilon
            )
            VolumeMod[:, 2] = multiplier * np.abs(bmax[:, 2] - bmin[:, 2])
            # Sposto solo gli estremi superiori delle variabili a destra
            bmax[:, 3] = Blockmax_numpy + step_width[:, 3]

            bmin[:, 3] = Blockmin_numpy.copy()
            bmax[bmax[:, 3] > 1, 3] = 1
            VolumeMod[:, 3] = multiplier * np.abs(bmax[:, 3] - bmin[:, 3])

            # determinare le sidebands dopo aver effettuato lo spostamento
            smin = np.zeros([len(subspace_indices), 4])
            smax = np.ones([len(subspace_indices), 4])
            excessvol_post_move = np.zeros([len(subspace_indices), 4])
            for i in range(4):
                for k in range(len(subspace_indices)):
                    smin[k, i] = bmin[k, i] * (1 + sidewidth) - sidewidth * bmax[k, i]
                    smax[k, i] = bmax[k, i] * (1 + sidewidth) - sidewidth * bmin[k, i]
                    smin[smin[k, i] < 0, i] = 0
                    smax[smax[k, i] > 1, i] = 1
                    excessvol_post_move[k, i] = (
                        excessvol_pre_move
                        * (
                            (bmax[k, i] - bmin[k, i])
                            / (Blockmax_numpy[k] - Blockmin_numpy[k])
                        )
                        / (
                            (smax[k, i] - smin[k, i])
                            / (Sidebands_max[k] - Sidebands_min[k])
                        )
                    )
            # ZPLtau
            if ZPLtau_alg_orig:
                # if num_events_sideband > 0:
                #    Zval_start = ZPLtau(
                #        num_events_block, num_events_sideband, excessvol_pre_move
                #    )
                # else:
                Zval_start = ZPL2(num_events_block, goodevents, VolumeOrig)
                # print(Zval_start)
                Zval_best = Zval_start
                ZPL = np.zeros(4)
                Nin_grad = np.zeros([len(subspace_indices), 4])
                side_grad = np.zeros([len(subspace_indices), 4])

                for k in range(len(subspace_indices)):
                    if stop_rule[k]:
                        continue
                    for m in range(4):
                        if not no_step[k, m]:
                            Block_min_tmp = Blockmin_numpy.copy()
                            Block_max_tmp = Blockmax_numpy.copy()
                            Block_min_tmp[k] = bmin[k, m]
                            Block_max_tmp[k] = bmax[k, m]
                            Side_min_tmp = Sidebands_min.copy()
                            Side_max_tmp = Sidebands_max.copy()
                            Side_min_tmp[k] = smin[k, m]
                            Side_max_tmp[k] = smax[k, m]
                            Nin_grad[k, m] = get_num_events(
                                Block_min_tmp, Block_max_tmp, X_numpy_smpl
                            )
                            side_grad[k, m] = (
                                get_num_events(Side_min_tmp, Side_max_tmp, X_numpy_smpl)
                                - Nin_grad[k, m]
                            )
                            # if side_grad[k, m] > 0:
                            #    ZPL[m] = ZPLtau(
                            #        Nin_grad[k, m],
                            #     side_grad[k, m],
                            #        excessvol_post_move[k, m],
                            #    )
                            # else:
                            # print(VolumeMod[k, m])
                            ZPL[m] = ZPL2(Nin_grad[k, m], goodevents, VolumeMod[k, m])
                            if ZPL[m] > Zval_best:
                                # differenza[m] = ZPL[m] - Zval_best
                                # print(f"m: {m}")
                                # print(f"differenza m: {differenza[m]}")
                                Zval_best = ZPL[m]
                                digrad = m
                                igrad = k
                if igrad == -1:
                    for k in range(len(subspace_indices)):
                        for m in range(4):
                            step_width[k, m] = step_width[k, m] - epsilon
                            if step_width[k, m] < epsilon:
                                step_width[k, m] = epsilon
                            if all(step_width[k, :] <= epsilon):
                                stop_rule[k] = True
                else:
                    Blockmin_numpy[igrad] = bmin[igrad, digrad]
                    Blockmax_numpy[igrad] = bmax[igrad, digrad]
                    Sidebands_min[igrad] = smin[igrad, digrad]
                    Sidebands_max[igrad] = smax[igrad, digrad]
                    for m in range(4):
                        if m != digrad:
                            step_width[k, m] = 0.8 * step_width[k, m]

                    if digrad == 0:
                        if Blockmin_numpy[0] > 0:
                            step_width[igrad, 0] = step_width[igrad, 0] * 1.5
                            if step_width[igrad, 0] > Blockmin_numpy[igrad]:
                                step_width[igrad, 0] = Blockmin_numpy[igrad]
                        else:
                            step_width[igrad, 0] = epsilon
                    if digrad == 1 or digrad == 2:
                        if Blockmax_numpy[igrad] - Blockmin_numpy[igrad] > epsilon:
                            step_width[igrad, digrad] = step_width[igrad, digrad] * 1.5
                            if step_width[igrad, digrad] > (
                                Blockmax_numpy[igrad] - Blockmin_numpy[igrad] - epsilon
                            ):
                                step_width[igrad, digrad] = (
                                    Blockmax_numpy[igrad]
                                    - Blockmin_numpy[igrad]
                                    - epsilon
                                )
                        else:
                            step_width[igrad, 0] = epsilon
                    if digrad == 3:
                        if Blockmax_numpy[igrad] < 1:
                            step_width[igrad, 3] = step_width[igrad, 3] * 1.5
                            if step_width[igrad, 3] > (1 - Blockmax_numpy[igrad]):
                                step_width[igrad, 3] = 1 - Blockmax_numpy[igrad]
                        else:
                            step_width[igrad, 3] = epsilon

        # calcolo qta' per output

        included_points = get_included_points_indices_subspace(
            Blockmin_numpy, Blockmax_numpy, subspace_indices, X_numpy
        )
        num_events_block_last = get_num_events(
            Blockmin_numpy, Blockmax_numpy, X_numpy_smpl
        )
        best_box_volume = (Blockmax_numpy - Blockmin_numpy).prod()
        best_sidebands_min, best_sidebands_max = sidebands(
            subspace_indices, Blockmin_numpy, Blockmax_numpy
        )
        best_VolumeSidebands = (best_sidebands_max - best_sidebands_min).prod()
        migliore_Z = Zval_best

        # stampare num eventi sidebands
        out[ntrial] = {
            "box_volume": best_box_volume,
            "box_vol_sidebands": best_VolumeSidebands,
            "box_IN": num_events_block_last,
            "box_ZPLtau": migliore_Z,
            "Blockmin": Blockmin_numpy,
            "Blockmax": Blockmax_numpy,
            "subspace_idx": subspace_indices,
            "included_points": included_points,
        }
    return out


if __name__ == "__main__":

    df = creazione_df(10000, 20, 15, np.array([0.01, 0.1]), 0.99)
    # df = pd.read_csv(r"dati_generati_tmp.csv.csv")
    X = df.loc[:, df.columns != "Signal"]
    X_array = X.values

    X_trasf = probability_integral_transform(X_array)

    X_df_trasf = pd.DataFrame(data=X_trasf, index=None, columns=X.columns)

    prova_start_time = time.perf_counter()
    prova = gradient_sequenziale(
        number_trials=1000,
        numbers_gd_loops=1000,
        soglia_pca=0.8,
        step_width_val=0.2,
        max_volume_box=0.25,
        X=X_df_trasf,
        PCA_opt=False,
        ZPLtau_alg_orig=True,
        numero_slices=10,
    )
    prova_time = time.perf_counter() - prova_start_time
    print(best_box(prova, df, 0.01), file=open("output.txt", "a"))
    print(prova_time)
