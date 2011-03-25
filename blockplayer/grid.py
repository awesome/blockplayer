import numpy as np
import preprocess
import opencl
import lattice
import carve
import config
import os

GRIDRAD = 18
bounds = (-GRIDRAD,0,-GRIDRAD),(GRIDRAD,8,GRIDRAD)


from ctypes import POINTER as PTR, c_byte, c_size_t, c_float
speedup_ctypes = np.ctypeslib.load_library('speedup_ctypes.so',
                                           os.path.dirname(__file__))
speedup_ctypes.histogram.argtypes = [PTR(c_byte), PTR(c_float), PTR(c_float),
                                     c_size_t, c_size_t, c_size_t, c_size_t]


def initialize():
    b_width = [bounds[1][i]-bounds[0][i] for i in range(3)]
    global vote_grid, carve_grid, keyvote_grid, keycarve_grid
    keyvote_grid = np.zeros(b_width)
    keycarve_grid = np.zeros(b_width)
    vote_grid = np.zeros(b_width)
    carve_grid = np.zeros(b_width)

    global shadow_blocks, solid_blocks, wire_blocks
    shadow_blocks = None
    solid_blocks = None
    wire_blocks = None

if not 'vote_grid' in globals(): initialize()


def refresh():
    global solid_blocks, shadow_blocks, wire_blocks
    #solid_blocks = carve.grid_vertices((occH>10))
    #shadow_blocks = carve.grid_vertices((vacH>10))
    solid_blocks = carve.grid_vertices((carve_grid<40)&(vote_grid>30))
    shadow_blocks = carve.grid_vertices((carve_grid>=30)&(vote_grid>30))
    wire_blocks = carve.grid_vertices((carve_grid>10))


def drift_correction(new_votes, new_carve):
    """ Using the current values for vote_grid and carve_grid,
    and the new histograms
    generated from the newest frame, find the translation between old and new 
    (in a 3x3 neighborhood, only considering jumps of 1 block) that minimizes 
    an error function between them.
    """
    def error(t):
        """ 
        t: x,y
        The error function is the number of error blocks that fall in a carved
        region.
        """
        nv = np.roll(new_votes, t[0], 0)
        nv = np.roll(nv, t[2], 2)
        nc = np.roll(new_carve, t[0], 0)
        nc = np.roll(nc, t[2], 2)
        return np.sum(np.minimum(nc,vote_grid) + np.minimum(nv,carve_grid) -
                      np.minimum(nv,vote_grid)/4)

    t = [(x,y,z) for x in [0,-1,1,-2,2] for y in [0] for z in [0,-1,1,-2,2]]
    vals = [error(_) for _ in t]
    #print vals
    return t[np.argmin(vals)], np.min(vals)


def depth_inds(modelmat, side='left'):    
    gridmin = bounds[0]
    gridmax = bounds[1]

    X,Y,Z = np.mgrid[gridmin[0]:gridmax[0],
                     gridmin[1]:gridmax[1],
                     gridmin[2]:gridmax[2]]+0.5
    X *= config.LW
    Y *= config.LH
    Z *= config.LW

    bg = config.bgL if side == 'left' else config.bgR

    mat = np.linalg.inv(np.dot(np.dot(modelmat,
                               bg['Ktable']),
                        bg['KK']))
    x = X*mat[0,0] + Y*mat[0,1] + Z*mat[0,2] + mat[0,3]
    y = X*mat[1,0] + Y*mat[1,1] + Z*mat[1,2] + mat[1,3]
    z = X*mat[2,0] + Y*mat[2,1] + Z*mat[2,2] + mat[2,3]
    w = X*mat[3,0] + Y*mat[3,1] + Z*mat[3,2] + mat[3,3]

    return x/w, y/w, z/w


def depth_sample(modelmat, depth, side='left'):
    gridmin = np.zeros((4,),'f')
    gridmax = np.zeros((4,),'f')
    gridmin[:3] = bounds[0]
    gridmax[:3] = bounds[1]

    # Find the reference depth for each voxel, and the sampled depth
    x,y,dref = depth_inds(modelmat, side)
    import scipy.ndimage
    d = scipy.ndimage.map_coordinates(depth, (y,x), order=0,
                                      prefilter=False,
                                      cval=2047)
    #d = depth[np.round(x).astype('i'),np.round(y).astype('i')]

    X,Y,Z = np.mgrid[gridmin[0]:gridmax[0],
                     gridmin[1]:gridmax[1],
                     gridmin[2]:gridmax[2]]+0.5

    # Project to metric depth
    mat = config.bgL['KK'] if side == 'left' else config.bgR['KK']
    z = x*mat[2,0] + y*mat[2,1] + d*mat[2,2] + mat[2,3]
    w = x*mat[3,0] + y*mat[3,1] + d*mat[3,2] + mat[3,3]
    dmet = z/w

    z = x*mat[2,0] + y*mat[2,1] + dref*mat[2,2] + mat[2,3]
    w = x*mat[3,0] + y*mat[3,1] + dref*mat[3,2] + mat[3,3]
    drefmet = z/w

    return x,y,d,dref, (d<2047)&(dmet<drefmet-(config.LH*2+config.LW)/3)


def add_votes_numpy(xfix, zfix, depthL, depthR):
    gridmin = np.zeros((4,),'f')
    gridmax = np.zeros((4,),'f')
    gridmin[:3] = bounds[0]
    gridmax[:3] = bounds[1]

    global X,Y,Z, XYZ
    X,Y,Z,face = np.rollaxis(opencl.get_modelxyz(),1)
    XYZ = np.array((X,Y,Z)).transpose()
    fix = np.array((xfix,0,zfix))
    cxyz = np.frombuffer(np.array(face).data,
                         dtype='i1').reshape(-1,4)[:,:3]
    global cx,cy,cz
    cx,cy,cz = np.rollaxis(cxyz,1)
    f1 = cxyz*0.5

    mod = np.array([config.LW, config.LH, config.LW])
    gi = np.floor(-gridmin[:3] + (XYZ-fix)/mod + f1)
    gi = np.array((gi, gi - cxyz))
    gi = np.rollaxis(gi, 1)

    global blahpt
    blahpt = (XYZ-fix)/mod+f1

    global gridinds
    gridinds = gi

    def get_gridinds():
        (L1,T1),(R1,B1) = opencl.rectL
        (L2,T2),(R2,B2) = opencl.rectR
        lengthL, lengthR = opencl.lengthL, opencl.lengthR
                
        return (gridinds[:lengthL,:,:].reshape(T1-B1,R1-L1,2,3),
                gridinds[lengthL:,:,:].reshape(T2-B2,R2-L2,2,3))

    global gridL, gridR
    gridL, gridR = get_gridinds()

    global inds
    inds = gridinds[np.any(cxyz!=0,1),:,:]
    #inds = gridinds[cy!=0,:,:]
    if len(inds) == 0: return

    global occH, vacH
    global carve_grid,vote_grid, bins
    bins = [np.arange(0,bounds[1][i]-bounds[0][i]+1) for i in range(3)]
    occH,_ = np.histogramdd(inds[:,0,:], bins)
    vacH,_ = np.histogramdd(inds[:,1,:], bins)

    # Add in the carved pixels
    _,_,_,_,carveL = depth_sample(lattice.modelmat,depthL,'left')
    _,_,_,_,carveR = depth_sample(lattice.modelmat,depthR,'right')
    #vacH *= 0
    vacH += 60 * (carveL | carveR)

    (bx,_,bz),err = drift_correction(occH, vacH)
    if (bx,bz) != (0,0):
        lattice.modelmat[0,3] += bx*config.LW
        lattice.modelmat[2,3] += bz*config.LW
        occH = np.roll(np.roll(occH, bx, 0), bz, 2)
        vacH = np.roll(np.roll(vacH, bx, 0), bz, 2)
        print "drift detected:", bx,bz

    wx,wy,wz = [bounds[1][i]-bounds[0][i] for i in range(3)]

    # occH = np.zeros((wx,wy,wz),'f')
    # vacH = np.zeros((wx,wy,wz),'f')
    # speedup_ctypes.histogram(gridinds.ctypes.data_as(PTR(c_byte)), 
    #                          occH.ctypes.data_as(PTR(c_float)),
    #                          vacH.ctypes.data_as(PTR(c_float)), 
    #                          np.int32(gridinds.shape[0]), 
    #                          np.int32(wx), np.int32(wy), np.int32(wz))

    if 0:
        sums = np.zeros((3,3),'f')
        speedup_ctypes.histogram_error(vote_grid.ctypes.data,
                                       carve_grid.ctypes.data, 
                                       occH.ctypes.data, vacH.ctypes.data, 
                                       sums.ctypes.data_as(PTR(c_float)),
                                       wx, wy, wz);
    carve_grid = np.maximum(vacH, carve_grid)
    vote_grid = np.maximum(occH, vote_grid)
    vote_grid[carve_grid>30] = 0
    refresh()

  
def add_votes_opencl(xfix,zfix):
    gridmin = np.zeros((4,),'f')
    gridmax = np.zeros((4,),'f')
    gridmin[:3] = bounds[0]
    gridmax[:3] = bounds[1]

    global occH, vacH
    global carve_grid,vote_grid

    opencl.compute_gridinds(xfix,zfix, config.LW, config.LH, gridmin, gridmax)
    global gridinds
    gridinds = opencl.get_gridinds()

    inds = gridinds[gridinds[:,0,3]!=0,:,:3]    
    if len(inds) == 0: return
  
    bins = [np.arange(0,bounds[1][i]-bounds[0][i]+1) for i in range(3)]
    occH,_ = np.histogramdd(inds[:,0,:], bins)
    vacH,_ = np.histogramdd(inds[:,1,:], bins)
    bx,_,bz = drift_correction(occH, vacH)
    if 0 and (bx,bz) != (0,0):
        lattice.modelmat[0,3] += bx*config.LW
        lattice.modelmat[2,3] += bz*config.LW
        print "drift detected:", bx,bz
        return lattice.modelmat[:3,:4]

    wx,wy,wz = [bounds[1][i]-bounds[0][i] for i in range(3)]

    # occH = np.zeros((wx,wy,wz),'f')
    # vacH = np.zeros((wx,wy,wz),'f')
    # speedup_ctypes.histogram(gridinds.ctypes.data_as(PTR(c_byte)), 
    #                          occH.ctypes.data_as(PTR(c_float)),
    #                          vacH.ctypes.data_as(PTR(c_float)), 
    #                          np.int32(gridinds.shape[0]), 
    #                          np.int32(wx), np.int32(wy), np.int32(wz))
    #sums = np.zeros((3,3),'f')

    refresh()
