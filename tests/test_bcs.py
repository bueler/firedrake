import pytest
import numpy as np
from firedrake import *


@pytest.fixture
def V():
    mesh = UnitSquareMesh(10, 10)
    V = FunctionSpace(mesh, "CG", 1)
    return V


@pytest.fixture
def u(V):
    return Function(V)


@pytest.fixture
def a(u, V):
    v = TestFunction(V)
    a = dot(grad(v), grad(u)) * dx
    return a


def test_homogeneous_bcs(a, u, V):
    bcs = [DirichletBC(V, 32, 1)]

    [bc.homogenize() for bc in bcs]
    # Compute solution - this should have the solution u = 0
    solve(a == 0, u, bcs=bcs)

    assert max(abs(u.vector().array())) == 0.0


def test_homogenize_doesnt_overwrite_function(a, u, V):
    f = Function(V)
    f.assign(10)
    bc = DirichletBC(V, f, 1)
    bc.homogenize()

    assert (f.vector().array() == 10.0).all()

    solve(a == 0, u, bcs=[bc])
    assert max(abs(u.vector().array())) == 0.0


def test_restore_bc_value(a, u, V):
    f = Function(V)
    f.assign(10)
    bc = DirichletBC(V, f, 1)
    bc.homogenize()

    solve(a == 0, u, bcs=[bc])
    assert max(abs(u.vector().array())) == 0.0

    bc.restore()
    solve(a == 0, u, bcs=[bc])
    assert np.allclose(u.vector().array(), 10.0)


def test_set_bc_value(a, u, V):
    f = Function(V)
    f.assign(10)
    bc = DirichletBC(V, f, 1)

    bc.set_value(7)

    solve(a == 0, u, bcs=[bc])

    assert np.allclose(u.vector().array(), 7.0)


def test_preassembly_change_bcs(V):
    v = TestFunction(V)
    u = TrialFunction(V)
    a = u*v*dx
    f = Function(V)
    f.assign(10)
    bc = DirichletBC(V, f, 1)

    A = assemble(a, bcs=[bc])
    L = v*f*dx
    b = assemble(L)

    y = Function(V)
    y.assign(7)
    bc1 = DirichletBC(V, y, 1)
    u = Function(V)

    solve(A, u, b)
    assert np.allclose(u.vector().array(), 10.0)

    u.assign(0)
    b = assemble(v*y*dx)
    solve(A, u, b, bcs=[bc1])
    assert np.allclose(u.vector().array(), 7.0)


def test_preassembly_doesnt_modify_assembled_rhs(V):
    v = TestFunction(V)
    u = TrialFunction(V)
    a = u*v*dx
    f = Function(V)
    f.assign(10)
    bc = DirichletBC(V, f, 1)

    A = assemble(a, bcs=[bc])
    L = v*f*dx
    b = assemble(L)

    b_vals = b.vector().array()

    u = Function(V)
    solve(A, u, b)
    assert np.allclose(u.vector().array(), 10.0)

    assert np.allclose(b_vals, b.vector().array())


@pytest.mark.xfail
def test_preassembly_bcs_caching(V):
    bc1 = DirichletBC(V, 0, 1)
    bc2 = DirichletBC(V, 1, 2)

    v = TestFunction(V)
    u = TrialFunction(V)

    a = u*v*dx

    Aboth = assemble(a, bcs=[bc1, bc2])
    Aneither = assemble(a)
    A1 = assemble(a, bcs=[bc1])
    A2 = assemble(a, bcs=[bc2])

    assert not np.allclose(Aboth.M.values, Aneither.M.values)
    assert not np.allclose(Aboth.M.values, A2.M.values)
    assert not np.allclose(Aboth.M.values, A1.M.values)
    assert not np.allclose(Aneither.M.values, A2.M.values)
    assert not np.allclose(Aneither.M.values, A1.M.values)
    assert not np.allclose(A2.M.values, A1.M.values)
    # There should be no zeros on the diagonal
    assert not any(A2.M.values.diagonal() == 0)
    assert not any(A1.M.values.diagonal() == 0)
    assert not any(Aneither.M.values.diagonal() == 0)


if __name__ == '__main__':
    import os
    pytest.main(os.path.abspath(__file__))
