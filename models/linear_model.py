"""
源码阅读，scikit-learn.linear_model中的线性回归实现

Generalized Linear models.

# Author: Alexandre Gramfort <alexandre.gramfort@inria.fr>
#         Fabian Pedregosa <fabian.pedregosa@inria.fr>
#         Olivier Grisel <olivier.grisel@ensta.org>
#         Vincent Michel <vincent.michel@inria.fr>
#         Peter Prettenhofer <peter.prettenhofer@gmail.com>
#         Mathieu Blondel <mathieu@mblondel.org>
#         Lars Buitinck <L.J.Buitinck@uva.nl>
#         Maryan Morel <maryan.morel@polytechnique.edu>
#
# License: BSD 3 clause
"""

import numpy as np
from __future__ import division
from abc import ABCMeta, abstractmethod
import numbers
import warnings

import numpy as np
import scipy.sparse as sp
from scipy import linalg
from scipy import sparse

from sklearn.utils import as_float_array, check_array, check_X_y,deprecated
from sklearn..utils import check_random_state, column_or_1d


"""
check_X_y: Input validation for standard estimators.

Checks X and y for consistent length, enforces X 2d and y 1d.
Standard input checks are only applied to y. For multi-label y,
set multi_output=True to allow 2d and sparse y.
If the dtype of X is object, attempt converting to float,
raising on failure.
# check_X_y 函数用于验证输入。检查X与y是否有一致的长度，并使X是2维，y为1维
    # 标准化输入检查仅用于y，对于多标签的y，设置multi_output=True ，并且允许y是2维稀疏的y
    # 如果X的类型为对象，则试图转换为float类型，如果不行就raise error

"""
def center_data(X, y, fit_intercept, normalize=False, copy=True,
                sample_weight=None):
    """
    Centers data to have mean zero along axis 0. This is here because
    nearly all linear models will want their data to be centered.

    If sample_weight is not None, then the weighted mean of X and y
    is zero, and not the mean itself

    这个函数用于将data沿着axis 0 将使其均值为0。
    因为几乎所有的线性模型都希望他们的数据被中心化。
    如果sample_weight不为空，那么X和y的加权均值将被置为0，而不是数据自己的均值。
    """
    X = as_float_array(X, copy)
    if fit_intercept:
        if isinstance(sample_weight, numbers.Number):
            sample_weight = None
            # 如果样本权重为数字，那么就为None？？？不接受这种量？应该为numpy array？？
        if sp.issparse(X):
            X_mean = np.zeros(X.shape[1])
            X_std = np.ones(X.shape[1])
            # 若X是稀疏的，那么就设X各属性的均值为0，且标准差为1。
            # 很自然地，稀疏矩阵中大多元素为0，所以假定其均值为0？？？
        else:
            # 若X不是稀疏矩阵，那么按X的axis = 0 （即沿着第一纬度对齐）计算其均值
            X_mean = np.average(X, axis=0, weights=sample_weight)
            X -= X_mean
            if normalize:
                # XXX: currently scaled to variance=n_samples
                X_std = np.sqrt(np.sum(X ** 2, axis=0))
                X_std[X_std == 0] = 1
                X /= X_std
            else:
                X_std = np.ones(X.shape[1])
        y_mean = np.average(y, axis=0, weights=sample_weight)
        y = y - y_mean
    else:
        X_mean = np.zeros(X.shape[1])
        X_std = np.ones(X.shape[1])
        y_mean = 0. if y.ndim == 1 else np.zeros(y.shape[1], dtype=X.dtype)
    return X, y, X_mean, y_mean, X_std





class LinearModel(six.with_metaclass(ABCMeta, BaseEstimator)):
    """Base class for Linear Models"""

    @abstractmethod
    def fit(self, X, y):
        """Fit model."""

    @deprecated(" and will be removed in 0.19.")
    def decision_function(self, X):
        """Decision function of the linear model.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape = (n_samples, n_features)
            Samples.

        Returns
        -------
        C : array, shape = (n_samples,)
            Returns predicted values.
        """
        return self._decision_function(X)

    def _decision_function(self, X):
        check_is_fitted(self, "coef_")

        X = check_array(X, accept_sparse=['csr', 'csc', 'coo'])
        return safe_sparse_dot(X, self.coef_.T,
                               dense_output=True) + self.intercept_

    def predict(self, X):
        """Predict using the linear model

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape = (n_samples, n_features)
            Samples.

        Returns
        -------
        C : array, shape = (n_samples,)
            Returns predicted values.
        """
        return self._decision_function(X)

    _center_data = staticmethod(center_data)

    def _set_intercept(self, X_mean, y_mean, X_std):
        """Set the intercept_
        """
        if self.fit_intercept:
            self.coef_ = self.coef_ / X_std
            self.intercept_ = y_mean - np.dot(X_mean, self.coef_.T)
        else:
            self.intercept_ = 0.


# XXX Should this derive from LinearModel? It should be a mixin, not an ABC.
# Maybe the n_features checking can be moved to LinearModel.
class LinearClassifierMixin(ClassifierMixin):
    """Mixin for linear classifiers.

    Handles prediction for sparse and dense X.
    """

    def decision_function(self, X):
        """Predict confidence scores for samples.

        The confidence score for a sample is the signed distance of that
        sample to the hyperplane.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape = (n_samples, n_features)
            Samples.

        Returns
        -------
        array, shape=(n_samples,) if n_classes == 2 else (n_samples, n_classes)
            Confidence scores per (sample, class) combination. In the binary
            case, confidence score for self.classes_[1] where >0 means this
            class would be predicted.
        """
        if not hasattr(self, 'coef_') or self.coef_ is None:
            raise NotFittedError("This %(name)s instance is not fitted "
                                 "yet" % {'name': type(self).__name__})

        X = check_array(X, accept_sparse='csr')

        n_features = self.coef_.shape[1]
        if X.shape[1] != n_features:
            raise ValueError("X has %d features per sample; expecting %d"
                             % (X.shape[1], n_features))

        scores = safe_sparse_dot(X, self.coef_.T,
                                 dense_output=True) + self.intercept_
        return scores.ravel() if scores.shape[1] == 1 else scores

    def predict(self, X):
        """Predict class labels for samples in X.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape = [n_samples, n_features]
            Samples.

        Returns
        -------
        C : array, shape = [n_samples]
            Predicted class label per sample.
        """
        scores = self.decision_function(X)
        if len(scores.shape) == 1:
            indices = (scores > 0).astype(np.int)
        else:
            indices = scores.argmax(axis=1)
        return self.classes_[indices]

    def _predict_proba_lr(self, X):
        """Probability estimation for OvR logistic regression.

        Positive class probabilities are computed as
        1. / (1. + np.exp(-self.decision_function(X)));
        multiclass is handled by normalizing that over all classes.
        """
        prob = self.decision_function(X)
        prob *= -1
        np.exp(prob, prob)
        prob += 1
        np.reciprocal(prob, prob)
        if prob.ndim == 1:
            return np.vstack([1 - prob, prob]).T
        else:
            # OvR normalization, like LibLinear's predict_probability
            prob /= prob.sum(axis=1).reshape((prob.shape[0], -1))
            return prob


class SparseCoefMixin(object):
    """Mixin for converting coef_ to and from CSR format.

    L1-regularizing estimators should inherit this.
    """

    def densify(self):
        """Convert coefficient matrix to dense array format.

        Converts the ``coef_`` member (back) to a numpy.ndarray. This is the
        default format of ``coef_`` and is required for fitting, so calling
        this method is only required on models that have previously been
        sparsified; otherwise, it is a no-op.

        Returns
        -------
        self: estimator
        """
        msg = "Estimator, %(name)s, must be fitted before densifying."
        check_is_fitted(self, "coef_", msg=msg)
        if sp.issparse(self.coef_):
            self.coef_ = self.coef_.toarray()
        return self

    def sparsify(self):
        """Convert coefficient matrix to sparse format.

        Converts the ``coef_`` member to a scipy.sparse matrix, which for
        L1-regularized models can be much more memory- and storage-efficient
        than the usual numpy.ndarray representation.

        The ``intercept_`` member is not converted.

        Notes
        -----
        For non-sparse models, i.e. when there are not many zeros in ``coef_``,
        this may actually *increase* memory usage, so use this method with
        care. A rule of thumb is that the number of zero elements, which can
        be computed with ``(coef_ == 0).sum()``, must be more than 50% for this
        to provide significant benefits.

        After calling this method, further fitting with the partial_fit
        method (if any) will not work until you call densify.

        Returns
        -------
        self: estimator
        """
        msg = "Estimator, %(name)s, must be fitted before sparsifying."
        check_is_fitted(self, "coef_", msg=msg)
        self.coef_ = sp.csr_matrix(self.coef_)
        return self


class LinearRegression(LinearModel, RegressorMixin):
    """
    Ordinary least squares Linear Regression.

    Parameters
    ----------
    fit_intercept : boolean, optional
        whether to calculate the intercept for this model. If set
        to false, no intercept will be used in calculations
        (e.g. data is expected to be already centered).
        这个参数决定是否对该模型计算截断
    normalize : boolean, optional, default False
        If True, the regressors X will be normalized before regression.
        这个参数若为True，那么回归因子X将在回归之前被规范化
    copy_X : boolean, optional, default True
        If True, X will be copied; else, it may be overwritten.
        这个参数若为True，X将被复制，否则将被覆盖
    n_jobs : int, optional, default 1
        The number of jobs to use for the computation.
        If -1 all CPUs are used. This will only provide speedup for
        n_targets > 1 and sufficient large problems.
        工作进程数量，如果设为大于1，将使用更多cpu内核计算
    Attributes
    ----------
    coef_ : array, shape (n_features, ) or (n_targets, n_features)
        Estimated coefficients for the linear regression problem.
        If multiple targets are passed during the fit (y 2D), this
        is a 2D array of shape (n_targets, n_features), while if only
        one target is passed, this is a 1D array of length n_features.
        这个属性是回归因子X的权重参数，即线性回归所希望求出的回归参数。
        该值可能是一维或二维的，如果输出结果y是一维的，那么coef即为一维向量（列表）；
        如果输出y为二维的，那么coef就是二维的列表（参数，特性）
    intercept_ : array
        Independent term in the linear model.
        这个属性是线性模型中的独立项，我猜是我方程中的b？？待查
    Notes
    -----
    From the implementation point of view, this is just plain Ordinary
    Least Squares (scipy.linalg.lstsq) wrapped as a predictor object.

    """

    def __init__(self, fit_intercept=True, normalize=False, copy_X=True,
                 n_jobs=1):
        self.fit_intercept = fit_intercept
        self.normalize = normalize
        self.copy_X = copy_X
        self.n_jobs = n_jobs

    @property
    @deprecated("``residues_`` is deprecated and will be removed in 0.19")
    def residues_(self):
        """Get the residues of the fitted model."""
        return self._residues

    def fit(self, X, y, sample_weight=None):
        """
        Fit linear model.
        拟合线性模型，即求解
        Parameters
        ----------
        X : numpy array or sparse matrix of shape [n_samples,n_features]
            Training data
            为numpy array或者，是形如【n个样本，n维属性】的稀疏矩阵，即训练集数据
        y : numpy array of shape [n_samples, n_targets]
            Target values
            形为【样本数，标记数】的numpy array，是标记数据（监督学习）
        sample_weight : numpy array of shape [n_samples]
            Individual weights for each sample
            样本权重，是一个长度为n_samples的numpy array，用于标记每个样本的权重，有此参数时各样本意义不同，或出现概率不同
            否则认为每个样本出现的概率是等可能的，属于等可能概型问题。
            .. versionadded:: 0.17
               parameter *sample_weight* support to LinearRegression.

        Returns
        -------
        self : returns an instance of self.
        """

        n_jobs_ = self.n_jobs
        X, y = check_X_y(X, y, accept_sparse=['csr', 'csc', 'coo'],
                         y_numeric=True, multi_output=True)

        if ((sample_weight is not None) and np.atleast_1d(sample_weight).ndim > 1):
            sample_weight = column_or_1d(sample_weight, warn=True)
            # 如果sample_weight 不为空且为二维数组，那么处理它使其一维化？？
        X, y, X_mean, y_mean, X_std = self._center_data(
            X, y, self.fit_intercept, self.normalize, self.copy_X,
            sample_weight=sample_weight)

        if sample_weight is not None:
            # Sample weight can be implemented via a simple rescaling.
            X, y = _rescale_data(X, y, sample_weight)

        if sp.issparse(X):
            if y.ndim < 2:
                out = sparse_lsqr(X, y)
                self.coef_ = out[0]
                self._residues = out[3]
            else:
                # sparse_lstsq cannot handle y with shape (M, K)
                outs = Parallel(n_jobs=n_jobs_)(
                    delayed(sparse_lsqr)(X, y[:, j].ravel())
                    for j in range(y.shape[1]))
                self.coef_ = np.vstack(out[0] for out in outs)
                self._residues = np.vstack(out[3] for out in outs)
        else:
            self.coef_, self._residues, self.rank_, self.singular_ = \
                linalg.lstsq(X, y)
            self.coef_ = self.coef_.T

        if y.ndim == 1:
            self.coef_ = np.ravel(self.coef_)
        self._set_intercept(X_mean, y_mean, X_std)
        return self

def _pre_fit(X, y, Xy, precompute, normalize, fit_intercept, copy):
    """Aux function used at beginning of fit in linear models"""
    n_samples, n_features = X.shape

    if sparse.isspmatrix(X):
        precompute = False
        X, y, X_mean, y_mean, X_std = sparse_center_data(
            X, y, fit_intercept, normalize)
    else:
        # copy was done in fit if necessary
        X, y, X_mean, y_mean, X_std = center_data(
            X, y, fit_intercept, normalize, copy=copy)
    if hasattr(precompute, '__array__') and (
            fit_intercept and not np.allclose(X_mean, np.zeros(n_features))
            or normalize and not np.allclose(X_std, np.ones(n_features))):
        warnings.warn("Gram matrix was provided but X was centered"
                      " to fit intercept, "
                      "or X was normalized : recomputing Gram matrix.",
                      UserWarning)
        # recompute Gram
        precompute = 'auto'
        Xy = None

    # precompute if n_samples > n_features
    if isinstance(precompute, six.string_types) and precompute == 'auto':
        precompute = (n_samples > n_features)

    if precompute is True:
        # make sure that the 'precompute' array is contiguous.
        precompute = np.empty(shape=(n_features, n_features), dtype=X.dtype,
                              order='C')
        np.dot(X.T, X, out=precompute)

    if not hasattr(precompute, '__array__'):
        Xy = None  # cannot use Xy if precompute is not Gram

    if hasattr(precompute, '__array__') and Xy is None:
        common_dtype = np.find_common_type([X.dtype, y.dtype], [])
        if y.ndim == 1:
            # Xy is 1d, make sure it is contiguous.
            Xy = np.empty(shape=n_features, dtype=common_dtype, order='C')
            np.dot(X.T, y, out=Xy)
        else:
            # Make sure that Xy is always F contiguous even if X or y are not
            # contiguous: the goal is to make it fast to extract the data for a
            # specific target.
            n_targets = y.shape[1]
            Xy = np.empty(shape=(n_features, n_targets), dtype=common_dtype,
                          order='F')
            np.dot(y.T, X, out=Xy.T)

    return X, y, X_mean, y_mean, X_std, precompute, Xy
