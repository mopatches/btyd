import warnings

from .fitters import BaseFitter
from .fitters.beta_geo_fitter import BetaGeoFitter
from .fitters.beta_geo_beta_binom_fitter import BetaGeoBetaBinomFitter
from .fitters.modified_beta_geo_fitter import ModifiedBetaGeoFitter
from .fitters.pareto_nbd_fitter import ParetoNBDFitter
from .fitters.gamma_gamma_fitter import GammaGammaFitter
from .fitters.beta_geo_covar_fitter import BetaGeoCovarsFitter
from .models import BaseModel, PredictMixin
from .models.beta_geo_model import BetaGeoModel
from .models.gamma_gamma_model import GammaGammaModel

__version__ = "0.1b2"

__all__ = (
    "__version__",
    "BetaGeoFitter",
    "ParetoNBDFitter",
    "GammaGammaFitter",
    "ModifiedBetaGeoFitter",
    "BetaGeoBetaBinomFitter",
    "BetaGeoCovarsFitter",
    "BetaGeoModel",
    "GammaGammaModel",
    )

def deprecated():
   warnings.warn("All Fitter models are deprecated and will be removed in the final stage of Beta development.", DeprecationWarning)

deprecated()
 